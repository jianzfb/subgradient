# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : schedule.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import docker
from subgradient.controller.cpu import *
from subgradient.controller.gpu import *
from subgradient import orm
from sqlalchemy import and_,or_


def schedule(resource_query):
  # 1.step look up free computing resource
  # 2.step apply computing resource
  # 3.step record in blockchain
  # 4.step return computing context (docker container)
  pass


class GradientContributer(object):
  cpu_quota = 1         #(unit)
  gpu_quota = 1         #(unit)
  cpu_mem_quota = 1     #(G)
  disk_quota = 1        #(G)

  def __init__(self, db):
    self.client = docker.from_env()
    self.db = db

  @property
  def running_container(self):
    running_containers = \
      self.db.query(orm.Container).filter(or_(orm.Container.health == 1,
                                              orm.Container.health == -1,
                                              orm.Container.health == -2)).all()

    return running_containers

  def free_cpu(self, running_containers):
    '''
    cpu_quota - occupied_cpu
    :return:
      free cpu num
    '''
    occupied_cpu = 0
    for container in running_containers:
      occupied_cpu += container.cpu_num

    return self.cpu_quota - occupied_cpu

  def free_cpu_memory(self, running_containers):
    '''
    cpu_mem_quota - occupied_mem
    :return:
      free cpu memory size
    '''
    occupied_cpu_mem = 0
    for container in running_containers:
      occupied_cpu_mem += container.cpu_mem

    return self.cpu_mem_quota - occupied_cpu_mem

  def free_gpu(self, running_containers):
    '''
    gpu_mem_quota - occupied_gpu
    :return:
      free gpu num
    '''
    occupied_gpu = 0
    for container in running_containers:
      occupied_gpu += container.gpu_num

    return self.gpu_quota - occupied_gpu

  def free_disk(self, running_containers):
    '''
    disk_quota - occupied_disk
    :return:
      free disk size
    '''
    occupied_disk = 0
    for container in running_containers:
      occupied_disk += container.disk_size

    return self.disk_quota - occupied_disk

  def _check_free_resource(self, cpu_num, cpu_memory, gpu_num, disk):
    '''
    check free resource
    :param cpu_num:       (unit)
    :param gpu_num:       (unit)
    :param cpu_memory:    (GB)
    :param disk:          (GB)
    :return:
    '''
    running_containers = self.running_container

    if not(cpu_num < self.free_cpu(running_containers) and
           cpu_memory < self.free_cpu_memory(running_containers) and
           gpu_num < self.free_gpu(running_containers) and
           disk < self.free_disk(running_containers)):
      return True

    return False

  def start(self, *args, **kwargs):
    # 0.step chek free resource
    is_resource_ok = self._check_free_resource(kwargs['cpu'],
                                               kwargs['cpu_mem'],
                                               kwargs['gpu'],
                                               kwargs['disk'])

    if not is_resource_ok:
      return None

    # 1.step pull or building image
    image_name = 'jupyterhub/singleuser'

    # 2.step warp container parameter
    host_config = dict()
    if 'volumes_bind':
      volume_bind = kwargs['volumes_bind']
      volume_binds = {}
      for k, v in volume_bind.items():
        volume_binds[k] = {'bind': v[0], 'mode': v[1]}
      host_config['volumes'] = volume_binds

    if 'cpu_mem' in kwargs:
      host_config['mem_limit'] = kwargs['cpu_mem']

    if 'cpu' in kwargs:
      host_config['cpu_period'] = 100000
      host_config['cpu_quota'] = 100000 * int(kwargs['cpu'])

    if 'working_dir' in kwargs:
      host_config['working_dir'] = kwargs['working_dir']

    cmd = None
    if 'cmd' in kwargs:
      cmd = kwargs['cmd']

    container = self.client.containers.run(image_name, command=cmd, **host_config)
    container_id = container['Id']
    print(container)

  def stop(self, *args, **kwargs):
    container_id = kwargs['container_id']
    container = self.client.containers.get(container_id)
    if container is not None:
      try:
        container.stop()
        container_db = self.db.query(orm.Container).filter(orm.Container.container_id==container_id).one_or_none()
        if container_db is not None:
          container_db.status = 0
          self.db.commit()
        return True
      except:
        container_db = self.db.query(orm.Container).filter(orm.Container.container_id==container_id).one_or_none()
        if container_db is not None:
          container_db.status = -3
          self.db.commit()
        return False
    else:
      return False

  def monitor(self, *args, **kwargs):
    pass

from collections import OrderedDict
if __name__ == '__main__':
  gs = GradientContributer()
  vb = {'/Users/jian/Downloads/mywork': ('/hello', 'rw')}
  gs.start(volumes_bind=vb,cpu_mem='1g',cpu=1)
  pass