# -*- coding: UTF-8 -*-
# @Time : 2018/7/10
# @File : api.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import requests
from traitlets.config import LoggingConfigurable
from traitlets import Unicode
from traitlets import Integer
import json
import os
from six.moves import urllib


class SubgradientServerAPI(LoggingConfigurable):
  server_ip = Unicode('127.0.0.1', help="").tag(config=True)
  server_port = Integer(9880, help="").tag(config=True)

  @property
  def ip(self):
    return self.server_ip

  @property
  def port(self):
    return self.server_port

  def __init__(self, token, **kwargs):
    super(SubgradientServerAPI, self).__init__(**kwargs)
    self._token = token

  def __getattr__(self, item):
    # if item not in ['snapshot', 'register', 'bridge']:
    #   raise NotImplementedError
    if item.startswith('_'):
      raise NotImplementedError

    def func(**kwargs):
      if item == 'download':
        download_url = 'http://%s:%d/api/download/%s?id=%s' % (self.server_ip,self.server_port,kwargs['filecategory'],str(kwargs['filename']))
        fpath, _ = urllib.request.urlretrieve(download_url, kwargs['filepath'])
        statinfo = os.stat(fpath)
        return statinfo

      result = None
      if item.startswith('post_'):
        request_url = 'http://%s:%d/api/%s' % (self.server_ip, self.server_port, item.replace('post_', ''))
        result = requests.post(request_url, kwargs, headers={'Authorization': self._token})
      elif item.startswith('get_'):
        request_url = 'http://%s:%d/api/%s' % (self.server_ip, self.server_port, item.replace('get_', ''))
        result = requests.get(request_url, kwargs, headers={'Authorization': self._token})
      else:
        request_url = 'http://%s:%d/api/%s' % (self.server_ip, self.server_port, item)
        result = requests.post(request_url, kwargs, headers={'Authorization': self._token})

      if result is None:
        return None

      if result.status_code not in [200, 201]:
        return {'result': 'fail', 'reason': 'UNKOWN_ERROR'}

      try:
        response = json.loads(result.content)
        return response
      except:
        return None

    return func
