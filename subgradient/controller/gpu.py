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
      driver_version = re.findall('(?<=Driver Version: )[\d.]+', content)[0]
      gpu_basic_info = re.findall('(?<=\|)[ ]+\d[ ]+\w+ \w+ \w+[ ]+\w+[ ]+(?=\|)', content)
      gpu_num = len(gpu_basic_info)
      self._gpu_cards = []
      for gpu_index in range(gpu_num):
        result = re.split('\s+', gpu_basic_info[gpu_index])
        self._gpu_cards.append(''.join([result[1], ' ', result[2], ' ', result[3]]))

      gpu_mem_info = re.findall('\d+MiB / \d+MiB', content)
      gpu_mem_usage = []
      self._gpu_mem_max = []
      for gpu_index in range(gpu_num):
        result = re.split('/', gpu_mem_info[gpu_index])
        mem_usage = re.findall('\d+', result[0])[0]
        mem_max = re.findall('\d+', result[1])[0]
        gpu_mem_usage.append(int(mem_usage))
        self._gpu_mem_max.append(int(mem_max) / 1024)
    except:
        self._is_gpu_ok = False

  def gpu_model_name(self, card_id=-1):
    if card_id == -1:
      return self._gpu_cards

    return self._gpu_cards[card_id]

  def gpu_physical_cards(self):
    return len(self._gpu_cards)

  def total_mem(self, card_id=-1):
    if card_id == -1:
      return self._gpu_mem_max

    return self._gpu_mem_max[card_id]

  def running_state(self,card_id, interval=10):
    if not self._is_gpu_ok:
      return None

    gpu_mem_usage_sampling = []
    gpu_util_sampling = []
    for _ in range(interval):
      content = subprocess.check_output('nvidia-smi')
      driver_version = re.findall('(?<=Driver Version: )[\d.]+',content)[0]
      gpu_basic_info = re.findall('(?<=\|)[ ]+\d[ ]+\w+ \w+ \w+[ ]+\w+[ ]+(?=\|)',content)
      gpu_num = len(gpu_basic_info)
      gpus=[]
      for gpu_index in range(gpu_num):
          result = re.split('\s+',gpu_basic_info[gpu_index])
          gpus.append(''.join([result[1],' ',result[2],' ',result[3]]))

      gpu_pwr_info = re.findall('\d+W / \d+W',content)
      gpu_pwr_usage=[]
      gpu_pwr_cap=[]
      for gpu_index in range(gpu_num):
          result = re.split('/',gpu_pwr_info[gpu_index])
          pwr_usage = re.findall('\d+',result[0])[0]
          pwr_cap = re.findall('\d+',result[1])[0]
          gpu_pwr_usage.append(int(pwr_usage))
          gpu_pwr_cap.append(int(pwr_cap))

      gpu_mem_info = re.findall('\d+MiB / \d+MiB',content)
      gpu_mem_usage=[]
      gpu_mem_max=[]
      for gpu_index in range(gpu_num):
          result = re.split('/',gpu_mem_info[gpu_index])
          mem_usage = re.findall('\d+',result[0])[0]
          mem_max = re.findall('\d+',result[1])[0]
          gpu_mem_usage.append(int(mem_usage))
          gpu_mem_max.append(int(mem_max))

      gpu_util = re.findall('\d+(?=%)',content)
      gpu_util = [int(util) for util in gpu_util]

      # sampling
      gpu_mem_usage_sampling.append(gpu_mem_usage[card_id] / 1024)
      gpu_util_sampling.append(gpu_util[card_id]/100)

      # sleep 2 second
      time.sleep(2)

    return {'mem_usage': float(np.mean(gpu_mem_usage_sampling)),
            'gpu_usage': float(np.mean(gpu_util_sampling))}
