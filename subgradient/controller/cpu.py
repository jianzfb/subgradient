# encoding=utf-8
# @Time    : 17-5-8
# @File    : cpu.py
# @Author  : jian<jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import re
import psutil
import os
import platform
import numpy.distutils.cpuinfo
import subprocess
unit = {'b':1, 'k':2**10, 'm':2**20, 'g':2**30}

class CPU(object):
  def __init__(self):
    # 1.step system info
    self._system = platform.system()
    self._is_windows = False
    self._is_linux = False
    self._is_macos = False
    if self._system == 'Windows':
      self._is_windows = True
    elif self._system == 'Linux':
      self._is_linux = True
    else:
      self._is_macos = True

    assert (self._is_linux or self._is_macos)

    # 2.step cpu info
    self._cpu_physical_cores = 0
    self._cpu_logical_cores = []
    self._cpu_model_name = []
    self._cpu_MHz = []
    if self._is_linux:
      with open('/proc/cpuinfo') as fd:
        line_content = fd.readline()
        while line_content.startswith('processor'):
          # parse processor basic info
          line_content = fd.readline()
          while not line_content.startswith('processor'):
            model_name = ''
            logical_cores = 0
            cpu_mhz = 0
            core_id = -1
            if line_content.startswith('model name'):
              model_name = line_content.split(':')[1].strip()
            elif line_content.startswith('cpu cores'):
              logical_cores = int(line_content.split(':')[1].strip())
            elif line_content.startswith('cpu MHz'):
              cpu_mhz = line_content.split(':')[1].strip()
            elif line_content.startswith('core id'):
              core_id = int(line_content.split(':')[1].strip())

            if core_id == 0:
              self._cpu_logical_cores.append(logical_cores)
              self._cpu_model_name.append(model_name)
              self._cpu_MHz.append(cpu_mhz)

            line_content = fd.readline()
        self._cpu_physical_cores = len(self._cpu_model_name)
    else:
      # only test at macbook pro 2017
      pipe = subprocess.Popen('/usr/sbin/system_profiler SPHardwareDataType', shell=True, stdout=subprocess.PIPE).stdout
      res = pipe.read()
      terms = res.decode('utf-8').split('\n')
      for t in terms:
        if t.startswith('      Processor Name'):
          k,v = t.split(':')
          self._cpu_model_name.append(v.strip())
        elif t.startswith('      Number of Processors'):
          k,v = t.split(':')
          self._cpu_physical_cores = int(v.strip())
        elif t.startswith('      Total Number of Cores'):
          k,v = t.split(':')
          self._cpu_logical_cores.append(int(v.strip()))
        elif t.startswith('      Processor Speed'):
          t,v = t.split(':')
          val,val_unit = v.strip().split(' ')
          if val_unit == 'GHz':
            self._cpu_MHz.append(float(val) * 1000)
          else:
            self._cpu_MHz.append(float(val))

  @property
  def cpu_physical_cores(self):
    return self._cpu_physical_cores

  def cpu_logical_cores(self, id=-1):
    if id == -1:
      return self._cpu_logical_cores

    return self._cpu_logical_cores[id]

  def cpu_model_name(self, id=-1):
    if id == -1:
      return self._cpu_model_name

    return self._cpu_model_name[id]

  def cpu_mhz(self, id=-1):
    if id == -1:
      return self._cpu_MHz

    return self._cpu_MHz[id]

  @property
  def available_mem(self):
    # unit GB
    mem = psutil.virtual_memory()
    return (mem.available) / (1024 * 1024 * 1024)

  @property
  def total_mem(self):
    # unit GB
    mem = psutil.virtual_memory()
    return mem.total / (1024 * 1024 * 1024)

  @property
  def available_disk(self):
    # unit GB
    return psutil.disk_usage('/').free / (1024 * 1024 * 1024)

  def running_state(self, pid, interval=10):
    p = psutil.Process(pid)
    mem_max = psutil.virtual_memory().total / unit['m']
    mem_usage = p.memory_percent() * 0.01 * mem_max
    cpu_usage = p.cpu_percent(interval=interval)
    return {'mem_usage': mem_usage, 'cpu_usage': cpu_usage}