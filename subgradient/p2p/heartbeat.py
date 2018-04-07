# -*- coding: UTF-8 -*-
# @Time : 07/04/2018
# @File : heartbeat.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from subgradient.p2p.base import *

class SubgradientHeartbeat(Base):
  def __init__(self):
    pass

  def process(self, *args, **kwargs):
    self.write()
    pass

