# -*- coding: UTF-8 -*-
# @Time : 2018/6/21
# @File : ntptime.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

from traitlets.config import LoggingConfigurable
from traitlets import Unicode
from traitlets import Integer
import requests
import json

class SubgradientNTP(LoggingConfigurable):
  ntp_ip = Unicode('127.0.0.1', help='').tag(config=True)
  ntp_port = Integer(9880, help='').tag(config=True)

  def __init__(self, **kwargs):
    super(SubgradientNTP, self).__init__(**kwargs)

    self.request_url = 'http://%s:%d/api/time'%(self.ntp_ip, self.ntp_port)

  def time(self):
    result = requests.get(self.request_url)

    if result.status_code in [200, 201]:
      try:
        time_content = json.loads(result.content)
        return time_content['time']
      except:
        return None
    else:
      return None