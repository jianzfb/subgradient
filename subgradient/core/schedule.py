# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : schedule.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import docker
from docker.errors import *
from subgradient.core.cpu import *
from subgradient.core.gpu import *
from subgradient import orm
from sqlalchemy import and_,or_
from traitlets.config import LoggingConfigurable
from traitlets import Integer
from traitlets import Float
from traitlets import List
from traitlets import Unicode
from subgradient.blockchain.chain import *
import uuid
import tarfile
import shutil
from sqlalchemy.orm import scoped_session


class SubgradientSchedule(LoggingConfigurable):
  cpu_quota = Integer(-1, help='''share cpu quota''').tag(config=True)                  #(unit)
  gpu_quota = List([], help='''share gpu quota''').tag(config=True)                     #(list)

  cpu_mem_quota = Integer(-1, help='''share cpu memory quota''').tag(config=True)       #(G)
  gpu_mem_quota = List([], help='''share gpu memory quota''').tag(config=True)          #(list)
  max_tenants = Integer(2, help='''max online tenants simutaneously''').tag(config=True)
  fee = Float(0.0, help='''resource fee''').tag(config=True)                            #($)
  sale_mode = Unicode('split', help='''sale mode''').tag(config=True)                   # split or whole

  workspace = Unicode('/home/mi/subgradient/workspace', help='''subgradient server workspace''').tag(config=True)

  def __init__(self, db, chain, **kwargs):
    super(SubgradientSchedule, self).__init__(**kwargs)
    self._db = db
    self._cpu = CPU()
    self._gpu = GPU()
    self._chain = chain
    self._subgradient_server = SubgradientServer(self, **kwargs)

    logical_cores_num = len(self.cpu.cpu_logical_cores())
    if self.cpu_quota < 0 or self.cpu_quota > logical_cores_num:
      self.cpu_quota = logical_cores_num

    total_mem = int(self.cpu.cpu_total_mem())
    if self.cpu_mem_quota < 0 or self.cpu_mem_quota > total_mem:
      self.cpu_mem_quota = total_mem
    
    if self.gpu.is_gpu_ok:
      if len(self.gpu_quota) == 0 or len(self.gpu_quota) > self.gpu.gpu_physical_cards():
        self.gpu_quota = [i for i in range(self.gpu.gpu_physical_cards())]
        # TODO: check gpu mem quota
        
    else:
      self.gpu_quota = []
      self.gpu_mem_quota = []
  
  @property
  def db(self):
    return self._db
  
  @property
  def cpu(self):
    return self._cpu

  @property
  def gpu(self):
    return self._gpu

  @property
  def subgradient_server(self):
    return self._subgradient_server

  @property
  def chain(self):
    return self._chain

  def _check_online_tenant(self):
    running_orders = \
      self.db.query(orm.Order).filter(orm.Order.status == 1).all()

    if self.max_tenants <= len(running_orders):
      return False

    return True

  def _check_free_resource(self, cpu_model, cpu, cpu_mem, gpu_model=None, gpu=None, gpu_mem=None):
    # 0.step look up db
    processing_orders = \
      self.db.query(orm.Order).filter(orm.Order.status == 1).all()

    # 1.step check cpu relevant resource
    # 1.1.step check request cpu model
    if cpu_model is not None:
      share_cpu_model_names = self.cpu.cpu_model_name()
      if cpu_model not in share_cpu_model_names:
        self.log.error('request cpu model not support by this node')
        return False

    # 1.2.step check request cpu number
    cpu = 1 if cpu is None else cpu
    occupied_cpu = 0
    for order in processing_orders:
      occupied_cpu += order.cpu_num

    if occupied_cpu > self.cpu_quota:
      self.log.error('now running servers have occupied more cpus')
      return False

    now_free_cpu = self.cpu_quota - occupied_cpu
    if now_free_cpu < cpu:
      self.log.error('have no enough cpus for request')
      return False

    # 1.3.step check request cpu memory
    cpu_mem = 1 if cpu_mem is None else cpu_mem
    occupied_cpu_mem = 0
    for order in processing_orders:
      occupied_cpu_mem += order.cpu_mem

    if occupied_cpu_mem > self.cpu_mem_quota:
      self.log.error('now running servers have occupied more cpu memory')
      return False

    now_free_cpu_mems = self.cpu_mem_quota - occupied_cpu_mem
    if now_free_cpu_mems < cpu_mem:
      self.log.error('have no enough cpu memory for request')
      return False

    # 2.step check gpu relevant resource
    if not self.gpu.is_gpu_ok:
      if gpu_model is not None and gpu_model != '':
        self.log.error('dont support gpu')
        return False
      
      if gpu is not None and gpu > 0:
        self.log.error('dont support gpu')
        return False
      
      if gpu_mem is not None and gpu_mem > 0:
        self.log.error('dont support gpu')
        return False

      return True

    # 2.1.step check request gpu model
    if gpu_model is not None:
      share_gpu_model_names = self.gpu.gpu_model_name()
      if gpu_model not in share_gpu_model_names:
        self.log.error('request gpu model not support by this node')
        return False

    # 2.2.step check request gpu number
    gpu = 0 if gpu is None else gpu
    occupied_gpu = 0
    for container in processing_orders:
      occupied_gpu += container.gpu_num

    if occupied_gpu > len(self.gpu_quota):
      self.log.error('now running servers have occupied more gpus')
      return False

    now_free_gpu = len(self.gpu_quota) - occupied_gpu
    if now_free_gpu < gpu:
      self.log.error('have no enough gpus for request')
      return False

    # 2.3.step check request gpu memory
    gpu_mem = 0 if gpu_mem is None else gpu_mem
    if gpu_mem > self.gpu.gpu_total_mem(0):
      self.log.error('have no enough gpu memory')
      return False

    return True

  def update(self, **kwargs):
    # 1.step check all containers
    processing_orders = \
      self.db.query(orm.Order).filter(orm.Order.status == 1).all()

    occupied_cpu_num = 0
    occupied_cpu_mem = 0
    occupied_gpu_num = 0
    occupied_gpu_mem = 0
    for order in processing_orders:
      occupied_cpu_num += order.cpu_num
      occupied_cpu_mem += order.cpu_mem
      occupied_gpu_num += order.gpu_num
      occupied_gpu_mem += order.gpu_mem

    # 2.step update free resource on blockchain
    free_cpu_num = self.cpu_quota - occupied_cpu_num
    if free_cpu_num <= 0:
      self.log.warning('no have enough free cpu')
      return False

    free_cpu_mem = self.cpu_mem_quota - occupied_cpu_mem
    if free_cpu_mem <= 0:
      self.log.warning('no have enough free memory')
      return False

    free_gpu_num = len(self.gpu_quota) - occupied_gpu_num
    free_gpu_num = free_gpu_num if free_gpu_num < 0 else 0
    free_gpu_mem = self.gpu.gpu_total_mem(0)

    self.chain.update({'gpu': free_gpu_num,
                       'cpu': free_cpu_num,
                       'cpu_mem': free_cpu_mem,
                       'gpu_mem': free_gpu_mem,
                       'status': 'online',
                       'fee': self.fee,
                       'strategy': self.sale_mode,
                       'timestamp': time.time(),
                       'type': 'resource'})
    return True

  def monitor(self, **kwargs):
    # 1.step check all containers
    processing_orders = \
      self.db.query(orm.Order).filter(or_(orm.Order.status == 1)).all()

    # 2.step update status on chain
    for order in processing_orders:
      status = self.subgradient_server.monitor(container_id=order.container_id)
      if status == 'running':
        order.status = 1    # running

        update_status = 'running'
        now_time = time.time()
        if (now_time - order.launch_time) / 3600 > order.rental_time:
          res = self.subgradient_server.stop(order.container_id)
          update_status = 'stop'

        # update chain
        self.chain.update({
          'type': 'computing',
          'timestamp': time.time(),
          'order': order.order,
          'orderedby': order.orderedby,
          'supplier': order.supplier,
          'fee': order.fee,
          'health': 1,
          'status': update_status,
          'content': {'cpu_model': order.cpu_model,
                      'cpu': order.cpu_num,
                      'cpu_mem': order.cpu_mem,
                      'gpu_model': order.gpu_model,
                      'gpu': order.gpu_num,
                      'gpu_mem': order.gpu_mem}
        })
      elif status == 'error':   # error exit
        order.status = -1
        # update chain
        self.chain.update({
          'type': 'computing',
          'timestamp': time.time(),
          'order': order.order,
          'orderedby': order.orderedby,
          'supplier': order.supplier,
          'fee': order.fee,
          'health': -1,
          'status': 'running',
          'content': {'cpu_model': order.cpu_model,
                      'cpu': order.cpu_num,
                      'cpu_mem': order.cpu_mem,
                      'gpu_model': order.gpu_model,
                      'gpu': order.gpu_num,
                      'gpu_mem': order.gpu_mem}
        })
      else:
        order.status = 0    # exit
        # update chain
        self.chain.update({
          'type': 'computing',
          'timestamp': time.time(),
          'order': order.order,
          'orderedby': order.orderedby,
          'supplier': order.supplier,
          'fee': order.fee,
          'health': 1,
          'status': 'stop',
          'content': {'cpu_model': order.cpu_model,
                      'cpu': order.cpu_num,
                      'cpu_mem': order.cpu_mem,
                      'gpu_model': order.gpu_model,
                      'gpu': order.gpu_num,
                      'gpu_mem': order.gpu_mem}
        })

    # 3.step update local db
    self.db.commit()

  def schedule(self, **kwargs):
    # 1.step check whether accept request
    # 1.1.step check online tenants
    if not self._check_online_tenant():
      self.log.warning('subgradient server has arrived max online tenants simutaneously')
      return False

    # 1.2.step check free resource
    cpu_model = kwargs['cpu_model'] if 'cpu_model' in kwargs else None
    cpu = kwargs['cpu'] if 'cpu' in kwargs else None
    cpu_mem = kwargs['cpu_mem'] if 'cpu_mem' in kwargs else None
    gpu_model = kwargs['gpu_model'] if 'gpu_model' in kwargs else None
    gpu = kwargs['gpu'] if 'gpu' in kwargs else None
    gpu_mem = kwargs['gpu_mem'] if 'gpu_mem' in kwargs else None
    is_resource_ok = self._check_free_resource(cpu_model, cpu, cpu_mem, gpu_model, gpu, gpu_mem)
    if not is_resource_ok:
      self.log.warning('subgradient server has no enough free resource')
      return False

    # 2.step launch subgradeint server
    try:
      processing_orders = \
        self.db.query(orm.Order).filter(or_(orm.Order.status == 1)).all()

      occupied_workspace = []
      for order in processing_orders:
        workspace_index = int(order.workspace.split('-')[1])
        occupied_workspace.append(workspace_index)

      free_workspace = ['user-%d-space'%i for i in range(self.max_tenants) if i not in occupied_workspace]
      kwargs.update({'workspace': os.path.join(self.workspace, free_workspace[0], 'workspace')})
      status = self.subgradient_server.start(**kwargs)

      if status is None:
        self.log.error('couldnt launch subgradient server')
        return False

      # wait heatbeat in 10 seconds
    except:
      self.log.error('couldnt launch subgradient server')
      return False
    
    container_id = status['container_id']
    self.subgradient_server.monitor(container_id=container_id)
    self.subgradient_server.stop(container_id=container_id)
    
    # 3.step write to blockchain
    s = self.chain.update({
      'type':         'computing',
      'timestamp':    time.time(),
      'order':        kwargs['order'],
      'orderedby':    kwargs['orderedby'],
      'supplier':     kwargs['supplier'],
      'rental_time':  kwargs['rental_time'],
      'launch_time':  status['launch_time'],
      'fee':          kwargs['fee'],
      'health':       1,
      'status':       'running',
      'content': {'cpu_model': kwargs['cpu_model'],
                  'cpu': kwargs['cpu'],
                  'cpu_mem': kwargs['cpu_mem'],
                  'gpu_model': kwargs['gpu_model'],
                  'gpu': kwargs['gpu'],
                  'gpu_mem': kwargs['gpu_mem']}
    })
    return s


class SubgradientServer(LoggingConfigurable):
  def __init__(self, schedule, **kwargs):
    super(SubgradientServer, self).__init__(**kwargs)
    self.client = docker.from_env(version='auto')
    self.client_api = self.client.api
    self.schedule = schedule
  
  @property
  def cpu(self):
    return self.schedule.cpu
    
  @property
  def gpu(self):
    return self.schedule.gpu
  
  @property
  def db(self):
    return self.schedule.db
    
  def start(self, *args, **kwargs):
    # 1.step prepare workspace
    # 1.1.step look up valid workspace and clean up
    workspace = kwargs['workspace']
    if os.path.exists(workspace):
      shutil.rmtree(workspace)
    
    os.makedirs(workspace)
    
    # 1.2.step release dependent files
    if 'tar' not in kwargs:
      self.log.error('code file not included in request')
      return None

    with open(os.path.join(workspace, 'code.tar.gz'), 'wb') as fp:
      fp.write(kwargs['tar'])

    with tarfile.open(os.path.join(workspace, 'code.tar.gz'), 'r:gz') as tar:
      tar.extractall(workspace)

    # clear tar.gz file
    os.remove(os.path.join(workspace, 'code.tar.gz'))

    # 2.step pull or build image
    # 2.1.step build image
    image_name = None
    if 'Dockerfile' in kwargs and kwargs['Dockerfile'] != '':
      with open(os.path.join(workspace, 'Dockerfile'), 'w') as fp:
        fp.write(kwargs['Dockerfile'])
      start = time.time()
      # build custom image
      image_name = str(uuid.uuid4())
      self.client_api.images.build(path=workspace, rm=True, tag=image_name)
      elapsed_time = time.time() - start

      self.log.info('elapsed %0.2fs to build custom image %s'%(elapsed_time, image_name))

    if image_name is None:
      # image_name = 'subgradient/%s'%kwargs['platform']
      image_name = 'ubuntu'
      # 2.2.step pull image
      start = time.time()
      self.client_api.pull(image_name, tag='latest')
      elapsed_time = time.time() - start

      self.log.info('elapsed %0.2fs to pull standard image %s'%(elapsed_time, image_name))

    # 3.step config container parameter
    # 3.1.step cmd
    cmd = kwargs['cmd'] if 'cmd' in kwargs else None

    # 3.2.step volume map
    working_dir = '/home/workspace'
    volumes_binds = {workspace: {'bind': working_dir, 'mode': 'rw'}}

    # 3.3.step host config
    host_config = {}
    host_config['mem_limit'] = '%dg'%int(kwargs['cpu_mem'])
    host_config['cpu_period'] = 100000
    host_config['cpu_quota'] = 100000 * int(kwargs['cpu'])
    host_config['port_bindings'] = {5001: 5001}

    # 3.4.step gpu config
    free_gpu = []
    if 'gpu' in kwargs and int(kwargs['gpu']) > 0:
      processing_orders = \
        self.db.query(orm.Order).filter(orm.Order.status == 1).all()

      occupied_gpu = []
      for cc in processing_orders:
        if cc.gpu_num > 0:
          occupied_gpu.extend(cc.gpu['cards'])

      free_gpu = [card_i for card_i in self.schedule.gpu_quota if card_i not in occupied_gpu]

      gpu_devices = ['/dev/nvidiactl',
                     '/dev/nvidia-uvm']
      for card_i in range(kwargs['gpu']):
        gpu_devices.append('/dev/nvidia%d'%free_gpu[card_i])

      host_config.update({
        'volume_driver': 'nvidia-docker',
        'devices': gpu_devices,
        'binds': {
          'nvidia_driver_%s'%self.gpu.driver_version: {'bind': '/usr/local/nvidia', 'mode': 'ro'},
          '/vault': {'bind': '/vault', 'mode': 'rw'},
        }
      })

    if 'binds' in host_config:
      host_config['binds'].update(volumes_binds)
    else:
      host_config['binds'] = volumes_binds

    volumes = []
    for _, volume_bind in host_config['binds'].items():
      volumes.append(volume_bind['bind'])
    
    host_config = self.client_api.create_host_config(**host_config)
    
    # 4.step start container
    start = time.time()
    container = self.client_api.create_container(image_name,
                                                 cmd,
                                                 host_config=host_config,
                                                 volumes=volumes,
                                                 detach=True,
                                                 working_dir=working_dir)
    self.client_api.start(container)
    elapsed_time = time.time() - start

    container_id = container['Id']
    self.log.info('elapsed %0.2fs to start container %s'%(elapsed_time, container_id))

    # 5.step record in local db
    launch_time = time.time()
    subgradient_container = orm.Order(container_id=container_id,
                                      image=image_name,
                                      cpu_model=kwargs['cpu_model'],
                                      cpu_num=kwargs['cpu'],
                                      cpu_mem=kwargs['cpu_mem'],
                                      launch_time=launch_time,
                                      fee=kwargs['fee'],
                                      health=1,
                                      status=1,
                                      rental_time=kwargs['rental_time'],
                                      workspace=workspace)
    
    if self.gpu.is_gpu_ok:
      subgradient_container.gpu = {'cards': free_gpu[:kwargs['gpu']]}
      subgradient_container.gpu_model = self.gpu.gpu_model_name(free_gpu[0])
      subgradient_container.gpu_num = kwargs['gpu']
      subgradient_container.gpu_mem = self.gpu.gpu_total_mem(free_gpu[0])
      
    self.db.add(subgradient_container)
    self.db.commit()

    return {'container_id': container_id, 'launch_time': launch_time}

  def stop(self, *args, **kwargs):
    container_id = kwargs['container_id']
    order = self.db.query(orm.Order).filter(orm.Order.container_id == container_id).one_or_none()
    if order is not None:
      try:
        res = self.client_api.stop(container_id)
        order.status = 0
        self.db.commit()
      except:
        order.status = -1
        self.db.commit()

    return True

  def monitor(self, *args, **kwargs):
    try:
      res = 'exit'
      container_status = self.client_api.inspect_container(kwargs['container_id'])
      if container_status != None:
        if container_status['State']['Running']:
          res = 'running'
        elif container_status['State']['Paused']:
          res = 'error'
        elif container_status['State']['Dead']:
          res = 'error'
        else:
          res = 'error'
      return res
    except:
      return None

def tar_hirarchy_folder(ff, hirarchy_folder, tar):
  if os.path.isfile(os.path.join('/home/mi/mio', hirarchy_folder, ff)):
    tar.add(os.path.join('/home/mi/mio', hirarchy_folder, ff),
            arcname=os.path.join(hirarchy_folder, ff))
  else:
    for f in os.listdir(os.path.join('/home/mi/mio', ff)):
      if f[0] == '.':
        continue

      tar_hirarchy_folder(f, os.path.join(hirarchy_folder, ff), tar)

if __name__ == '__main__':
  # gs = GradientContributer()
  # vb = {'/Users/jian/Downloads/mywork': ('/hello', 'rw')}
  # gs.start(volumes_bind=vb,cpu_mem='1g',cpu=1)
  # client = docker.from_env(version='auto')
  # client.containers.run()
  # client.api.create_host_config()
  # client.api.create_container()
  all_files = os.listdir('/home/mi/mio')

  tar = tarfile.open('/home/mi/mio/mm.tar.gz', 'w:gz')
  for file in all_files:
    if file[0] == '.':
      continue

    if os.path.isfile(os.path.join('/home/mi/mio', file)):
      tar.add(os.path.join('/home/mi/mio', file), arcname=file)
    else:
      tar_hirarchy_folder(file, '', tar)

  tar.close()

  # content = ''
  # with open('/home/mi/mio/mm.tar.gz', 'rb') as fp:
  #   content = fp.read()
  #
  # db = scoped_session(orm.new_session_factory())()
  # chain = Chain()
  # ss = SubgradientSchedule(db,chain)
  # ss.schedule(cpu_model=None,
  #             cpu=1,
  #             cpu_mem=1,
  #             gpu_model=None,
  #             gpu=0,
  #             gpu_mem=0,
  #             Dockerfile='',
  #             tar=content,
  #             cmd='sleep 10000',
  #             platform='tensorflow',
  #             fee=0.0,
  #             rental_time=10,
  #             order='xxx',
  #             orderedby='bbb',
  #             supplier='ccc',
  # )