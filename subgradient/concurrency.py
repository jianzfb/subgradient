# -*- coding: UTF-8 -*-
# @Time : 2018/6/17
# @File : concurrency.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import threading
import functools

class StoppableThread(threading.Thread):
  """
  A thread that has a 'stop' event.
  """

  def __init__(self, evt=None):
    super(StoppableThread, self).__init__()
    if evt is None:
      evt = threading.Event()
    self._stop_evt = evt

  def stop(self):
    """ stop the thread"""
    self._stop_evt.set()

  def stopped(self):
    """ check whether the thread is stopped or not"""
    return self._stop_evt.isSet()

class SimpleStoppableThread(threading.Thread):
  def __init__(self, func):
    super(SimpleStoppableThread, self).__init__()
    self.func = func

  def run(self):
    try:
      self.func()
    except:
      # ignore
      pass


def thread_wrap(func):
  def _func(*args, **kwargs):
    stoppable_thread = SimpleStoppableThread(functools.partial(func, *args, **kwargs))
    stoppable_thread.start()

  return _func