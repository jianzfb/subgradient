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
from subgradient.subgrad.chain import *
import uuid
import tarfile
import shutil
from sqlalchemy.orm import scoped_session
from subgradient.utils import *
from subgradient.concurrency import *
from six.moves import urllib
from qiniu import Auth, put_file, etag, urlsafe_base64_encode
from subgradient.context import *
from subgradient.core import speedtest
from subgradient.core import disktest


class SubgradientSchedule(LoggingConfigurable):
  cpu_quota = Integer(0, help='''share cpu quota''').tag(config=True)                         #(unit)
  gpu_quota = List([], help='''share gpu quota''').tag(config=True)                           #(list)
  cpu_mem_quota = Integer(0,help='''share cpu memory quota''').tag(config=True)               #(G)
  gpu_mem_quota = Integer(-1,help='''share gpu memory quota''').tag(config=True)              #(list)                              #($)

  def __init__(self, db, workspace, **kwargs):
    super(SubgradientSchedule, self).__init__(**kwargs)
    self._db = db
    self._subgradient_server = SubgradientServer(self, **kwargs)
    self._workspace = workspace

    # 1.step analysis cpu resource
    self.log.info('analysis cpu resource')
    self._cpu = CPU()
    logical_cores_num = len(self.cpu.cpu_logical_cores())
    if self.cpu_quota <= 0 or self.cpu_quota > logical_cores_num:
      self.cpu_quota = logical_cores_num

    total_mem = int(self.cpu.cpu_total_mem())
    if self.cpu_mem_quota <= 0 or self.cpu_mem_quota > total_mem:
      self.cpu_mem_quota = total_mem

    # 2.step analysis gpu resource
    self.log.info('analysis gpu resource')
    self._gpu = GPU()
    if self.gpu.is_gpu_ok:
      if len(self.gpu_quota) == 0 or len(self.gpu_quota) > self.gpu.gpu_physical_cards():
        self.gpu_quota = [i for i in range(self.gpu.gpu_physical_cards())]
      self.gpu_mem_quota = self.gpu.gpu_total_mem(0)
    else:
      self.gpu_quota = []
      self.gpu_mem_quota = 0

    # 3.step analysis disk io speed
    disk_result = disktest.shell()
    disk_read_speed, disk_read_speed_unit = disk_result['read']
    if disk_read_speed_unit == 'GB/s':
      disk_read_speed = float(disk_read_speed) * 1024.0
    elif disk_read_speed_unit == 'KB/s':
      disk_read_speed = float(disk_read_speed) / 1024.0

    disk_write_speed, disk_write_speed_unit = disk_result['write']
    if disk_write_speed_unit == 'GB/s':
      disk_write_speed = float(disk_write_speed) * 1024.0
    elif disk_write_speed_unit == 'KB/s':
      disk_write_speed = float(disk_write_speed) * 1024.0

    self.disk_read = disk_read_speed
    self.disk_write = disk_write_speed

    # 4.step analysis net speed (skip)
    #download_speed, upload_speed = speedtest.shell()
    download_speed, upload_speed = 0.0,0.0
    self.upload_speed = upload_speed
    self.download_speed = download_speed

    if not os.path.exists(self.workspace):
      os.makedirs(self.workspace)
  
  @property
  def db(self):
    return self._db

  @property
  def workspace(self):
    return self._workspace

  @property
  def cpu(self):
    return self._cpu

  @property
  def gpu(self):
    return self._gpu

  @property
  def schedule_cpu_quota(self):
    return self.cpu_quota

  @property
  def schedule_gpu_quota(self):
    return self.gpu_quota

  @property
  def schedule_cpu_mem_quota(self):
    return self.cpu_mem_quota

  @property
  def schedule_gpu_mem_quota(self):
    return self.gpu_mem_quota

  @property
  def net_speed(self):
    # unit Mbit/s
    return self.upload_speed, self.download_speed

  @property
  def disk_speed(self):
    return self.disk_read, self.disk_write

  @property
  def subgradient_server(self):
    return self._subgradient_server

  def _check_free_resource(self, processing_orders, cpu_model, cpu_num, cpu_mem, gpu_model=None, gpu_num=None, gpu_mem=None):
    # 1.step check cpu relevant resource
    # 1.1.step check request cpu model (临时注释)
    if cpu_model is not None:
      share_cpu_model_names = self.cpu.cpu_model_name()
      if cpu_model not in share_cpu_model_names:
        self.log.error('request cpu model not support by this node')
        return False

    # 1.2.step check request cpu number
    cpu_num = 1 if cpu_num is None else cpu_num
    occupied_cpu = 0
    for order in processing_orders:
      occupied_cpu += order.stock.cpu_num

    if occupied_cpu > self.cpu_quota:
      self.log.error('now running servers have occupied more cpus')
      return False

    now_free_cpu = self.cpu_quota - occupied_cpu
    if now_free_cpu < cpu_num:
      self.log.error('have no enough cpus for request')
      return False

    # 1.3.step check request cpu memory
    cpu_mem = 1 if cpu_mem is None else cpu_mem
    occupied_cpu_mem = 0
    for order in processing_orders:
      occupied_cpu_mem += order.stock.cpu_mem

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
      
      if gpu_num is not None and gpu_num > 0:
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
    gpu_num = 0 if gpu_num is None else gpu_num
    occupied_gpu = 0
    for container in processing_orders:
      occupied_gpu += container.gpu_num

    if occupied_gpu > len(self.gpu_quota):
      self.log.error('now running servers have occupied more gpus')
      return False

    now_free_gpu = len(self.gpu_quota) - occupied_gpu
    if now_free_gpu < gpu_num:
      self.log.error('have no enough gpus for request')
      return False

    # 2.3.step check request gpu memory
    gpu_mem = 0 if gpu_mem is None else gpu_mem
    if gpu_mem > self.gpu.gpu_total_mem(0):
      self.log.error('have no enough gpu memory')
      return False

    return True


  def schedule_step_1_resource_check(self, order_info):
    # 1.step check free resource
    processing_orders = \
      self.db.query(orm.Order).filter(or_(orm.Order.status == 1,
                                          orm.Order.status == 2)).all()
    processing_orders = [mm for mm in processing_orders if mm != order_info['order']]

    running_config = order_info['running_config']
    platform_config = order_info['platform_config']
    order = order_info['order']

    cpu_model = order.stock.cpu_model
    cpu_num = order.stock.cpu_num
    cpu_mem = order.stock.cpu_mem
    gpu_model = order.stock.gpu_model
    gpu_num = order.stock.gpu_num
    gpu_mem = order.stock.gpu_mem
    is_resource_ok = self._check_free_resource(processing_orders,
                                               cpu_model,
                                               cpu_num,
                                               cpu_mem,
                                               gpu_model,
                                               gpu_num,
                                               gpu_mem)

    if is_resource_ok:
      order.status = 2
      self.db.commit()
    else:
      order.status = -1
      self.db.commit()
      self.log.error('%s: cpu %d mem %d gpu %d gpu_mem %d'%('NO_RESOURCE', cpu_num, cpu_mem, gpu_num, gpu_mem))
      return {'result': 'fail',
              'reason': 'NO_RESOURCE_ERROR',
              'order': order}

    # 2.step assign custom workspace
    order_workspace = os.path.join(self.workspace, order.name)
    if not os.path.exists(order_workspace):
      os.makedirs(order_workspace)

    running_config.update({'workspace': order_workspace})
    return {'result': 'NOT_DONE_YET',
            'processing_orders': processing_orders,
            'running_config': running_config,
            'platform_config': platform_config,
            'order': order,}

  def schedule_step_2_launch_container(self, order_info):
    if order_info['result'] == 'fail':
      return order_info

    order = order_info['order']
    try:
      running_config = order_info['running_config']
      platform_config = order_info['platform_config']

      result = self.subgradient_server.start(order, running_config, platform_config)
      result.update(order_info)
      return result
    except:
      order.status = -1
      self.db.commit()
      self.log.error('UNKOWN_ERROR: couldnt launch subgradient server')
      return {'result': 'fail',
              'reason': 'UNKOWN_ERROR',
              'order': order}

  def schedule(self, order_info):
    # 1.step free resource check
    step_1_result = self.schedule_step_1_resource_check(order_info)
    # 2.step launch container
    step_2_result = self.schedule_step_2_launch_container(step_1_result)
    return step_2_result

  def dummy_schedule(self, order_info):
    # here, couldnt continue to shedule order
    order_info['order'].status = -1
    self.db.commit()

  @thread_wrap
  def schedule_download_files(self, order_id, code_address, code_address_code=None):
    workspace = os.path.join(self.workspace, order_id)
    if not os.path.exists(workspace):
      os.makedirs(workspace)

    if code_address is None or code_address == '':
      with open(os.path.join(workspace, 'download.success'), 'w'):
        pass
      return

    if code_address.startswith('ipfs:'):
      # download from ipfs
      response = ipfs_download(code_address.replace('ipfs:'), workspace)
      if response:
        self.log.info('IPFS_DONWLOAD_SUCCESS: download dependent files for order %s' % order_id)
        try:
          with tarfile.open(os.path.join(workspace, 'code.tar.gz'), 'r:gz') as tar:
            tar.extractall(workspace)

          with open(os.path.join(workspace, 'download.success'), 'w'):
            pass
        except:
          # clear incomplete data
          # if os.path.exists(os.path.join(workspace, 'code')):
          #   shutil.rmtree(os.path.join(workspace, 'code'))
          if os.path.exists(os.path.join(workspace, 'code.tar.gz')):
            os.remove(os.path.join(workspace, 'code.tar.gz'))
          self.log.error('IPFS_DOWNLOAD_ERROR: for order %s' % order_id)
          with open(os.path.join(workspace, 'download.fail'), 'w'):
            pass
      else:
        # clear incomplete data
        if os.path.exists(os.path.join(workspace, 'code.tar.gz')):
          os.remove(os.path.join(workspace, 'code.tar.gz'))
        self.log.error('IPFS_DOWNLOAD_ERROR: for order %s'%order_id)
        with open(os.path.join(workspace, 'download.fail'), 'w'):
          pass
    elif code_address.startswith('qiniu:'):
      access_key = 'ZSC-X2p4HG5uvEtfmn5fsTZ5nqB3h54oKjHt0tU6'
      secret_key = 'Ya8qYwIDXZn6jSJDMz_ottWWOZqlbV8bDTNfCGO0'
      q = Auth(access_key, secret_key)
      base_url = code_address.replace('qiniu:','')
      private_url = q.private_download_url(base_url, expires=3600)
      key = base_url.split('/')[-1]     # code.tar.gz

      try:
        fpath, _ = urllib.request.urlretrieve(private_url, os.path.join(workspace, key))
        statinfo = os.stat(fpath)
        size = statinfo.st_size

        if size == 0:
          self.log.error('FILE_DOWNLOAD_ERROR: empty file for order %s'%order_id)
        else:
          try:
            if code_address_code is not None:
              decrypto_shell = 'openssl enc -d -aes256 -in %s -out %s -k %s' % (key,
                                                                                key.replace('_ssl', ''),
                                                                                code_address_code)
              subprocess.call(decrypto_shell, shell=True, cwd=workspace)

            with tarfile.open(os.path.join(workspace, key.replace('_ssl', '')), 'r:gz') as tar:
              tar.extractall(workspace)

            if os.path.getsize(os.path.join(workspace, key.replace('_ssl', ''))) == 0:
              self.log.error('FILE_DOWNLOAD_ERROR: for order %s' % order_id)
              with open(os.path.join(workspace, 'download.fail'), 'w'):
                pass
              return

            # clear tar file
            os.remove(os.path.join(workspace, key.replace('_ssl', '')))
            os.remove(os.path.join(workspace, key))

            self.log.info('FILE_DONWLOAD_SUCCESS: download dependent files for order %s' % order_id)
            with open(os.path.join(workspace, 'download.success'), 'w'):
              pass
          except:
            # clear incomplete data
            # if os.path.exists(os.path.join(workspace, 'code')):
            #   shutil.rmtree(os.path.join(workspace, 'code'))
            # if os.path.exists(os.path.join(workspace, 'code.tar.gz')):
            #   os.remove(os.path.join(workspace, 'code.tar.gz'))
            self.log.error('FILE_DOWNLOAD_ERROR: for order %s' % order_id)
            with open(os.path.join(workspace, 'download.fail'), 'w'):
              pass
      except:
        self.log.error('FILE_DOWNLOAD_ERROR: for order %s' % order_id)
        with open(os.path.join(workspace, 'download.fail'), 'w'):
          pass


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

  def start(self, order, running_config, platform_config):
    # 1.step user workspace
    workspace = running_config['workspace']

    # 2.step build image
    # 2.0.step check image existed
    image_list = self.client_api.images(order.image_name)
    image_tag = None
    image_name = None
    if len(image_list) == 0:
      # 2.1.step build image (user first connect, dont have custom private image)
      image_name = None
      if os.path.exists(os.path.join(workspace, 'Dockerfile')):
        # using custom dockerfile
        try:
          start = time.time()
          image_name = order.image_name
          self.client_api.images.build(path=workspace, rm=True, tag=image_name)
          elapsed_time = time.time() - start
          self.log.info('BUILD_IMAGE_SUCCESS: elapsed %0.2fs to build custom image %s for order %s'%(elapsed_time, image_name, order.name))
        except:
          order.status = -1
          self.db.commit()
          self.log.error('BUILD_IMAGE_ERROR: build custom image error for order %s'%order.name)
          return {'result': 'fail',
                  'reason': 'BUILD_IMAGE_ERROR'}

        has_image_list = self.client_api.images(order.image_name)
        if len(has_image_list) == 0:
          order.status = -1
          self.db.commit()
          self.log.error('BUILD_IMAGE_ERROR: build custom image error for order %s' % order.name)
          return {'result': 'fail',
                  'reason': 'BUILD_IMAGE_ERROR'}

      if image_name is None:
        # using standard image
        software_framework = platform_config['software_framework'] if 'software_framework' in platform_config else None
        os_platform = platform_config['os_platform'] if 'os_platform' in platform_config else 'ubuntu'
        os_version = platform_config['os_version'] if 'os_version' in platform_config else '14.04'

        base_image = None
        support_gpu = True if order.stock.gpu_num > 0 else False
        if os_platform != '' and os_version != '' and software_framework != '':
          base_image = self.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                      orm.ImageRepository.os_version == os_version,
                                                                      orm.ImageRepository.software_framework == software_framework,
                                                                      orm.ImageRepository.support_gpu == support_gpu)).first()
        elif os_platform != '' and os_version != '':
          base_image = self.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                      orm.ImageRepository.os_version == os_version,
                                                                      orm.ImageRepository.support_gpu == support_gpu)).first()
        elif os_platform != '' and software_framework != '':
          base_image = self.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                      orm.ImageRepository.software_framework == software_framework,
                                                                      orm.ImageRepository.support_gpu == support_gpu)).first()
        elif os_platform != '':
          base_image = self.db.query(orm.ImageRepository).filter(
            and_(orm.ImageRepository.os_platform == os_platform,
                 orm.ImageRepository.support_gpu == support_gpu)).first()
        elif software_framework != '':
          base_image = self.db.query(orm.ImageRepository).filter(
            and_(orm.ImageRepository.software_framework == software_framework,
                 orm.ImageRepository.support_gpu == support_gpu)).first()
        elif os_platform == '' and os_version == '' and software_framework == '':
          base_image = self.db.query(orm.ImageRepository).filter(orm.ImageRepository.support_gpu==support_gpu).first()

        if base_image is None:
          order.status = -1
          self.db.commit()
          self.log.error('NO_IMAGE_ORDER: no valid image for order %s' % order.name)
          return

        image_name = base_image.image_name
        ab = image_name.split(':')
        if len(ab) == 2:
          image_name, image_tag = ab
    else:
      image_name = order.image_name

    # 3.step config container parameter
    # 3.1.step cmd
    cmd = running_config['cmd'] if 'cmd' in running_config else 'sleep 20m'
    # write run.sh at workspace
    with open(os.path.join(workspace, 'run.sh'), 'w') as fp:
      fp.write('export IPFS_HOST="%s"\n'%host_ip())
      if cmd != '/usr/sbin/sshd -D':
        # update key codebase
        fp.write('bash /update.sh')
        # run client command
        fp.write('nohup %s > task.log 2>&1 &\n'%cmd)
      if order.stock.gpu_num > 0:
        # config cuda link
        fp.write('ln -s /usr/local/nvidia/lib64/libnvidia-ml.so.%s /lib/x86_64-linux-gnu/libnvidia-ml.so\n'%self.gpu.driver_version)
        fp.write('ldconfig\n')
      # launch ssh server
      fp.write('/usr/sbin/sshd -D')
    cmd = 'bash /home/workspace/run.sh'

    # 3.2.step volume map
    working_dir = '/home/workspace'
    data_dir = '/dataset'
    volumes_binds = {workspace: {'bind': working_dir, 'mode': 'rw'},
                     os.path.join(get_global_context().workspace, 'dataset', 'factory'): {'bind': data_dir, 'mode': 'ro'}}

    # 3.3.step host config
    host_config = {}
    cpu_mem = order.stock.cpu_mem
    cpu_num = order.stock.cpu_num
    host_config['mem_limit'] = '%dg'%int(cpu_mem)
    host_config['cpu_period'] = 100000
    host_config['cpu_quota'] = 100000 * int(cpu_num)
    host_config['port_bindings'] = {}
    if 'port_bindings' in running_config:
      host_config['port_bindings'].update(running_config['port_bindings'])

    # 3.4.step gpu config
    free_gpu = []
    if order.stock.gpu_num > 0:
      processing_orders = \
        self.db.query(orm.Order).filter(or_(orm.Order.status == 1,
                                            orm.Order.status == 2)).all()

      occupied_gpu = []
      for cc in processing_orders:
        if cc.stock.gpu_num > 0 and 'gpu' in cc.running_config:
          occupied_gpu.extend(cc.running_config['gpu'])

      free_gpu = [card_i for card_i in self.schedule.gpu_quota if card_i not in occupied_gpu]
      gpu_devices = ['/dev/nvidiactl',
                     '/dev/nvidia-uvm']

      running_config['gpu'] = []
      for card_i in range(order.stock.gpu_num):
        gpu_devices.append('/dev/nvidia%d'%free_gpu[card_i])
        running_config['gpu'].append(free_gpu[card_i])

      # assign order gpu
      order.running_config = {}
      self.db.commit()
      order.running_config = running_config
      self.db.commit()

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

    try:
      host_config = self.client_api.create_host_config(**host_config)
      self.log.info('CREATE_CONTAINER_SUCCESS: success config host parameter')
    except:
      order.status = -1
      self.db.commit()
      self.log.error('CREATE_CONTAINER_ERROR: host config maybe not correct for order %s'%order.name)
      return {'result': 'fail',
              'reason': 'CREATE_CONTAINER_ERROR'}
    
    # 4.step start container
    try:
      start = time.time()
      image_name_and_tag = '%s:%s'%(image_name,image_tag) if image_tag is not None else image_name
      export_port = []
      if 'port_bindings' in running_config:
        for k,v in running_config['port_bindings'].items():
          export_port.append(k)

      container = self.client_api.create_container(image_name_and_tag,
                                                   cmd,
                                                   ports=export_port,
                                                   host_config=host_config,
                                                   volumes=volumes,
                                                   working_dir=working_dir,
                                                   environment=running_config['ENV'] if 'ENV' in running_config else {})
      self.client_api.start(container)
      elapsed_time = time.time() - start

      container_id = container['Id']
      order.status = 1
      order.health = 1
      order.container_id = container_id
      self.db.commit()

      self.log.info('START_CONTAINER_SUCCESS: elapsed %0.2fs to start container %s for order %s' % (elapsed_time, container_id, order.name))
      return {'result': 'success', 'reason': '',}
    except:
      order.status = -1
      self.db.commit()
      self.log.error('START_CONTAINER_ERROR: couldnt start container for order %s'%order.name)
      return {'result': 'fail',
              'reason': 'START_CONTAINER_ERROR'}

  def stop(self, order):
    if order is not None:
      try:
        #
        self.client_api.stop(order.container_id)
        order.status = 3
        self.db.commit()
        self.log.info('stop container %s of order id %s'%(order.container_id, order.name))
      except:
        order.status = -1
        self.db.commit()
        self.log.error('fail to stop container %s of order id %s'%(order.container_id, order.name))

    return True

  def monitor(self, order):
    if order.container_id == '':
      return 'error'

    try:
      res = 'exit'
      container_status = self.client_api.inspect_container(order.container_id)
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
      return 'error'

def tar_hirarchy_folder(ff, hirarchy_folder, tar):
  if os.path.isfile(os.path.join('/home/mi/mio', hirarchy_folder, ff)):
    tar.add(os.path.join('/home/mi/mio', hirarchy_folder, ff),
            arcname=os.path.join(hirarchy_folder, ff))
  else:
    for f in os.listdir(os.path.join('/home/mi/mio', ff)):
      if f[0] == '.':
        continue

      tar_hirarchy_folder(f, os.path.join(hirarchy_folder, ff), tar)
