# -*- coding: UTF-8 -*-
# @Time : 07/04/2018
# @File : base.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from traitlets.config import LoggingConfigurable
from traitlets import Integer
from traitlets import Float
from traitlets import List
from traitlets import Unicode
from subgradient.context import *
from subgradient.p2p.protocol import *


class Base(LoggingConfigurable):
  def __init__(self):
    self.ctx = get_global_context()
    pass

  @property
  def schedule(self):
    return getattr(self.ctx, 'schedule', None)

  @property
  def protocol(self):
    return ''

  def process(self, *args, **kwargs):
    raise NotImplementedError

  def write(self, content=None):
    self.protocol.content = content
    pass