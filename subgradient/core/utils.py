# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : utils.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

SUBGRADIENT_FAIL_REASON = {
  'TENANT_LIMIT_ERROR': 'arrive max tenants',
  'NO_RESOURCE_ERROR': 'server have no enough free resource',
  'IPFS_DOWNLOAD_ERROR': 'fail to downlaod from ipfs',
  'FILE_DOWNLOAD_ERROR': 'fail to download',
  'FILE_OR_FOLDER_EXIST_ERROR': 'couldnt find relevant file or folder',
  'BUILD_IMAGE_ERROR':'',
  'INVALID_ORDER':'',
  'NO_SIGNED_ORDER':'',
  'NO_IMAGE_ORDER':'',
  'PULL_IMAGE_ERROR':'',
  'CREATE_CONTAINER_ERROR':'',
  'START_CONTAINER_ERROR':'',
  'INVALID_ACCESS_TOKEN_ERROR': '',
  'EXPIRE_ACCESS_TOKEN_ERROR':'',
  'RELAUNCH_ERROR': 'server has been running or waiting to schedule',
  'EXPIRE_RENTAL_ERROR': '',
  'REAUTHORIZE_ERROR':'',
  'EXPIRE_RENTAL_OR_TERMINATE_ERROR':'',
  'SIGNATURE_CONSISTENT_ERROR':'',
  'NO_CONTAINER_ERROR':'',
  'NO_DOCKERFILE_ERROR':'',
  'IMAGE_NAME_NOT_UNIQUE':'',
  'EXCEED_DISK_QUOTA_ERROR':'',
  'UNKOWN_ERROR': 'unkown',
}

SUBGRADIENT_SUCCESS_REASON = {
  'IPFS_DONWLOAD_SUCCESS': '',
  'FILE_DONWLOAD_SUCCESS': '',
  'BUILD_IMAGE_SUCCESS': '',
  'PULL_IMAGE_SUCCESS':'',
  'CREATE_CONTAINER_SUCCESS': '',
  'START_CONTAINER_SUCCESS':'',
}

