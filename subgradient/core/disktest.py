# -*- coding: UTF-8 -*-
# @Time : 2018/7/11
# @File : disktest.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import os
import subprocess
import numpy as np
import logging
from subgradient.core.operation_system import *

def _run_shell(cmd):
  p = subprocess.Popen(args=cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
  p.wait()
  return p.stdout.read()


def _parse_write_disk_speed(result):
  '''
  1024+0 records in
  1024+0 records out
  1073741824 bytes (1.1 GB) copied, 3.7433 s, 287 MB/s
  '''
  last_line = result.strip().split('/n')[-1]
  kv_terms = last_line.split(',')[-1].strip().split(' ')
  speed = kv_terms[0]
  speed_unit = kv_terms[1]

  return speed, speed_unit


def _parse_read_disk_speeds(result):
  last_line = result.strip().split('/n')[-1]
  kv_terms = last_line.split(',')[-1].strip().split(' ')
  speed = kv_terms[0]
  speed_unit = kv_terms[1]

  return speed, speed_unit


def shell():
  subgradient_operation_system = OperationSystem()
  if subgradient_operation_system.is_linux:
    # 1.step test write speed (GB/s, MB/s)
    disk_write_speed = []
    disk_write_speed_unit = ''
    for try_index in range(3):
      logging.info('try %d time for testing disk write' %try_index)
      write_result = _run_shell('dd if=/dev/zero of=test.out bs=1M count=1024')
      speed, speed_unit = _parse_write_disk_speed(write_result)

      disk_write_speed.append(float(speed))
      disk_write_speed_unit = speed_unit

    disk_write_speed = np.mean(disk_write_speed)

    # 2.step test read speed (GB/s, MB/s)
    disk_read_speed = []
    disk_read_speed_unit = ''
    for try_index in range(3):
      logging.info('try %d time for testing disk read' %try_index)
      read_result = _run_shell('dd if=test.out of=/dev/null bs=1M count=1024')
      speed, speed_unit = _parse_read_disk_speeds(read_result)

      disk_read_speed.append(float(speed))
      disk_read_speed_unit = speed_unit

    disk_read_speed = np.mean(disk_read_speed)

    return {'read': (disk_read_speed, disk_read_speed_unit),
            'write': (disk_write_speed, disk_write_speed_unit)}
  else:
    return {'read': (0,''), 'write': (0,'')}