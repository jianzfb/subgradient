# -*- coding: UTF-8 -*-
# @Time : 2018/6/1
# @File : image.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import docker
import os
from traitlets.config import LoggingConfigurable
from traitlets import Unicode
import time
from subgradient import orm
import tarfile
import zipfile
import shutil

class ImageManage(LoggingConfigurable):
  def __init__(self, db, workspace, **kwargs):
    super(ImageManage, self).__init__(**kwargs)
    self._db = db
    self._workspace = workspace
    self.client = docker.from_env(version='auto')
    self.dockerfile_folder = os.path.join(workspace, 'dockerfile')

    if not os.path.exists(self.dockerfile_factory):
      os.makedirs(self.dockerfile_factory)

  @property
  def dockerfile_factory(self):
    return self.dockerfile_folder

  def build_image(self, building_folder, image_name, **kwargs):
    # 0.step parse necessary parameters
    # 1.step untar or do nothing
    # copy pub
    if not os.path.exists(os.path.join(self._workspace, 'secret', 'secret.subgrad.pub')):
      self.log.error('BUILD_IMAGE_ERROR: dont have secret.subgrad.pub')
      return False

    if not os.path.exists(os.path.join(self.dockerfile_folder, building_folder)):
      return False

    try:
      if 'tar.gz' in os.path.normpath(building_folder):
        with tarfile.open(os.path.join(self.dockerfile_folder, building_folder), 'r:gz') as tar:
          random_folder, dockerfile_folder = os.path.normpath(building_folder).split('/')
          def is_within_directory(directory, target):
              
              abs_directory = os.path.abspath(directory)
              abs_target = os.path.abspath(target)
          
              prefix = os.path.commonprefix([abs_directory, abs_target])
              
              return prefix == abs_directory
          
          def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
          
              for member in tar.getmembers():
                  member_path = os.path.join(path, member.name)
                  if not is_within_directory(path, member_path):
                      raise Exception("Attempted Path Traversal in Tar File")
          
              tar.extractall(path, members, numeric_owner=numeric_owner) 
              
          
          safe_extract(tar, os.path.join(self.dockerfile_folder,random_folder))
          building_folder = '%s/%s'%(random_folder, dockerfile_folder.replace(".tar.gz", ""))

      elif 'zip' in os.path.normpath(building_folder):
        with zipfile.ZipFile(os.path.join(self.dockerfile_folder, building_folder), 'r') as fp:
          random_folder, dockerfile_folder = os.path.normpath(building_folder).split('/')
          fp.extractall(path=os.path.join(self.dockerfile_folder, random_folder))
          building_folder = '%s/%s'%(random_folder, dockerfile_folder.replace(".zip", ""))

      if not os.path.isdir(os.path.join(self.dockerfile_folder, building_folder)):
        self.log.error('BUILD_IMAGE_ERROR: %s is not a folder' % building_folder)
        return False

      if not os.path.exists(os.path.join(self.dockerfile_folder, building_folder, 'Dockerfile')):
        self.log.error('BUILD_IMAGE_ERROR: dont have Dockerfile')
        return False

      shutil.copy(os.path.join(self._workspace, 'secret', 'secret.subgrad.pub'),
                  os.path.join(self.dockerfile_folder, building_folder))

      # 2.step build image
      # start building
      start = time.time()
      self.client.images.build(path=os.path.join(self.dockerfile_folder, building_folder), rm=True, tag=image_name)
      elapsed_time = time.time() - start
      self.log.info('BUILD_IMAGE_SUCCESS: elapsed %0.2fs to build base image %s' % (elapsed_time, image_name))
    except:
      self.log.error('BUILD_IMAGE_ERROR: build custom image error')
      return False

    return True


  def image_status(self, image_name):
    try:
      docker_image = self.client.images.get(image_name)
      if docker_image is None:
        return {'result': 'synchronize error'}
      else:
        return {'result': 'existed'}
    except:
      return {'result': 'not existed'}

if __name__ == '__main__':
  image_manage = ImageManage(None)
  # image_manage.build_image('AA.tar.gz', 'meme')
  image_manage.image_status('hello')
  # pass
