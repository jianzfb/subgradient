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
  return global_context


class Context(object):
  def __init__(self, **kwargs):
    global global_context
    global_context = self

    for k,v in kwargs.items():
      setattr(self, k, v)
    self._thread_pool = {}

  def reigster_thread(self, thread_handler, **kwargs):
    self.thread_pool[thread_handler] = kwargs

  def remove_thread(self, thread_handler):
    self.thread_pool.pop(thread_handler)

  @property
  def thread_pool(self):
    return self._thread_pool
