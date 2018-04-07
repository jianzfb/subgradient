# -*- coding: UTF-8 -*-
# @Time : 07/04/2018
# @File : order.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from subgradient.p2p.base import *
import json

class SubgradientOrder(Base):
  def __init__(self):
    pass

  def _check_param(self, **kwargs):
    return True

  def process(self, *args, **kwargs):
    response = self.schedule.schedule(kwargs)
    self.write(json.dumps({'order': 'success' if response else 'fail'}))