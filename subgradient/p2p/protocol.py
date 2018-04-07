# -*- coding: UTF-8 -*-
# @Time : 07/04/2018
# @File : protocol.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import subgradient
import json

class Protocol(object):
  def __init__(self):
    pass

  @property
  def version(self):
    return subgradient.__version__

  def serialize(self):
    return ''