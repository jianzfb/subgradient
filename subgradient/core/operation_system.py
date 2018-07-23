# -*- coding: UTF-8 -*-
# @Time : 2018/7/11
# @File : operation_system.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import platform


class OperationSystem():
  def __init__(self):
    self._system = platform.system()

  @property
  def system(self):
    return self._system

  @property
  def is_windows(self):
    return self._system == 'Windows'

  @property
  def is_linux(self):
    return self._system == 'Linux'

  @property
  def is_macos(self):
    return self._system != 'Windows' and self._system != 'Linux'