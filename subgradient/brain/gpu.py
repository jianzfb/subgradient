#!/usr/bin/env python
# -*- coding: utf-8 -*-
# File: gpu.py
# Author: jian<jian@mltalker.com>
from __future__ import unicode_literals

import os
import re
# from antgo.utils.utils import change_env
import subprocess
import time
import numpy as np


class GPU(object):
  def __init__(self):
    try:
      content = subprocess.check_output('nvidia-smi')

      self._is_gpu_ok = True
      self._driver_version = re.findall('(?<=Driver Version: )[\d.]+', content)[0]
      gpu_cards_basic_info = re.findall('(?<=\|)[ ]+\d+%[ ]+\d+C[]+\w+\d+W / /d+W[ ]+(?=\|)', content)
      gpu_num = len(gpu_cards_basic_info)
      self._gpu_cards = []
      for gpu_index in range(gpu_num):
        result = re.split('\s+', gpu_cards_basic_info[gpu_index].strip())
        self._gpu_cards.append(result[2])

      gpu_mem_info = re.findall('\d+MiB / \d+MiB', content)
      self._gpu_mem_max = []
      for gpu_index in range(gpu_num):
        result = re.split('/', gpu_mem_info[gpu_index])
        mem_max = re.findall('\d+', result[1])[0]
        self._gpu_mem_max.append(float(mem_max) / 1024)
    except:
        self._is_gpu_ok = False

  @property
  def driver_version(self):
    if not self.is_gpu_ok:
      return None

    return self._driver_version

  @property
  def is_gpu_ok(self):
    return self._is_gpu_ok

  def gpu_model_name(self, card_id=-1):
    if not self.is_gpu_ok:
      return None

    if card_id == -1:
      return self._gpu_cards

    return self._gpu_cards[card_id]

  def gpu_physical_cards(self):
    if not self.is_gpu_ok:
      return None

    return len(self._gpu_cards)

  def gpu_total_mem(self, card_id=-1):
    if not self.is_gpu_ok:
      return None

    if card_id == -1:
      return self._gpu_mem_max

    return self._gpu_mem_max[card_id]

  def gpu_available_mem(self, card_id=-1):
    if not self.is_gpu_ok:
      return None

    try:
      content = subprocess.check_output('nvidia-smi')
      gpu_mem_info = re.findall('\d+MiB / \d+MiB', content)
      gpu_mem_usage = []

      for gpu_index in range(self.gpu_physical_cards()):
        result = re.split('/', gpu_mem_info[gpu_index])
        mem_usage = re.findall('\d+', result[0])[0]
        gpu_mem_usage.append(float(mem_usage) / 1024)

      if card_id == -1:
        return gpu_mem_usage

      return gpu_mem_usage[card_id]
    except:
      return None

  def gpu_util(self, card_id=-1):
    if not self.is_gpu_ok:
      return None

    content = subprocess.check_output('nvidia-smi')
    gpu_util = re.findall('(?<=\|)[ ]+\d+(?=%)', content)
    gpu_util = [int(util) for id, util in enumerate(gpu_util) if id % 2 == 1]

    if card_id == -1:
      return gpu_util

    return gpu_util[card_id]

  def running_state(self, pid, interval=10):
    if not self._is_gpu_ok:
      return None

    content = subprocess.check_output('nvidia-smi')
    pattern = '(?<=\|)[ ]+\d+[ ]+\s+(?={pid})'.format(pid=pid)
    terms = re.findall(pattern,content)
    occupy_gpus = []
    for term in terms:
        occupy_gpus.append(int(term.strip()))

    if len(occupy_gpus) == 0:
      return None

    for _ in range(interval):
      content = subprocess.check_output('nvidia-smi')

      gpu_pwr_info = re.findall('\d+W / \d+W',content)
      gpu_pwr_usage=[]
      gpu_pwr_cap=[]
      for gpu_index in range(self.gpu_physical_cards()):
          result = re.split('/',gpu_pwr_info[gpu_index])
          pwr_usage = re.findall('\d+',result[0])[0]
          pwr_cap = re.findall('\d+',result[1])[0]
          gpu_pwr_usage.append(float(pwr_usage))
          gpu_pwr_cap.append(float(pwr_cap))

      gpu_mem_info = re.findall('\d+MiB / \d+MiB',content)
      gpu_mem_usage=[]
      gpu_mem_max=[]
      for gpu_index in range(self.gpu_physical_cards()):
          result = re.split('/',gpu_mem_info[gpu_index])
          mem_usage = re.findall('\d+',result[0])[0]
          mem_max = re.findall('\d+',result[1])[0]
          gpu_mem_usage.append(float(mem_usage))
          gpu_mem_max.append(float(mem_max))

      gpu_util = re.findall('(?<=\|)[ ]+\d+(?=%)', content)
      gpu_util = [int(util) for id, util in enumerate(gpu_util) if id % 2 == 1]

      pid_mem_util = np.mean([gpu_mem_usage[id] / gpu_mem_max[id] for id in occupy_gpus])
      pid_gpu_util = np.mean([gpu_util[id] / 100.0 for id in occupy_gpus])
      pid_pwr_util = np.mean([gpu_pwr_usage[id] / gpu_pwr_cap[id] for id in occupy_gpus])

      # sleep 2 second
      time.sleep(2)

    return {'mem_util': pid_mem_util, 'gpu_util': pid_gpu_util, 'gpu_pwr': pid_pwr_util}

# my_gpu = GPU()
# print(my_gpu.gpu_model_name())
# print(my_gpu.gpu_available_mem())
# print(my_gpu.gpu_available_mem(1))
# print(my_gpu.gpu_util())
# print(my_gpu.driver_version)
#
# print(my_gpu.running_state(6465, 1))
# print(my_gpu.gpu_util())