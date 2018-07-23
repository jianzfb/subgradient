# -*- coding: UTF-8 -*-
# @Time : 2018/7/18
# @File : appinstance.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import os
import tempfile
import logging

class AppInstance(object):
  # specify the file used to save the application instance pid
  def __init__(self, app_name):
    self.pid_file = os.path.join(tempfile.gettempdir(),'%s.pid'%app_name)
    self.check()
    self.start_app()

  # check if the current application is already running
  def check(self):
    # check if the pidfile exists
    if not os.path.isfile(self.pid_file):
      return

    # read the pid from the file
    pid = 0
    try:
      file = open(self.pid_file, 'rt')
      data = file.read()
      file.close()
      pid = int(data)
    except:
      pass

    # check if the process with specified by pid exists
    if 0 == pid:
      return

    try:
      os.kill(pid, 0)  # this will raise an exception if the pid is not valid
    except:
      return

    # exit the application
    logging.info("The application is already running !")
    exit(0)  # exit raise an exception so don't put it in a try/except block

  # called when the single instance starts to save it's pid
  def start_app(self):
    file = open(self.pid_file, 'wt')
    file.write(str(os.getpid()))
    file.close()

  # called when the single instance exit ( remove pid file )
  def exit_app(self):
    try:
      os.remove(self.pid_file)
    except:
      pass
