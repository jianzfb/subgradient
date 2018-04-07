# -*- coding: UTF-8 -*-
# @Time : 07/04/2018
# @File : context.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

global_context = None


def get_global_context():
  global global_context
  assert(global_context is not None)
  return global_context

class Context(object):
  def __init__(self):
    pass