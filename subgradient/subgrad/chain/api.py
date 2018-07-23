# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : api.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import os
import requests
from traitlets.config import LoggingConfigurable
from traitlets import Unicode
from traitlets import Integer
import json
import time
from subgradient.context import *

class SubgradientChainAPI(LoggingConfigurable):
  server_ip = Unicode('127.0.0.1', help="").tag(config=True)
  server_port = Integer(9880, help="").tag(config=True)

  def __init__(self, secret, **kwargs):
    super(SubgradientChainAPI, self).__init__(**kwargs)
    self.wallet_secret = secret

  @property
  def public_key(self):
    try:
      with open('%s/secret.subgrad.pub'%self.wallet_secret) as fp:
        public_key = fp.read()
        return public_key
    except:
      return None

  @property
  def private_key(self):
    try:
      with open('%s/secret.subgrad'%self.wallet_secret) as fp:
        private_key = fp.read()
        return private_key
    except:
      return None

  @property
  def money(self):
    info = self.rpc_get()
    if info is None:
      return {'money': 0, 'frozen_money': 0}
    return {'money': info['money'], 'frozen_money': info['frozen_money']}

  def keygen(self, forced=False):
    if not os.path.exists(os.path.join(self.wallet_secret,'secret.subgrad')):
      if not os.path.exists(self.wallet_secret):
        os.makedirs(self.wallet_secret)

      os.popen('ssh-keygen -t rsa -P "" -f %s/secret.subgrad -C ""'%(self.wallet_secret)).read()
    elif forced:
      # 1.step rename old secret
      now_time_str = time.strftime('%Y%m%d%H%M%S', time.localtime(time.time()))
      if os.path.exists(os.path.join(self.wallet_secret, 'secret.subgrad')):
        os.rename(os.path.join(self.wallet_secret, 'secret.subgrad'), os.path.join(self.wallet_secret, '%s_secret.subgrad'%now_time_str))

      if os.path.exists(os.path.join(self.wallet_secret, 'secret.subgrad.pub')):
        os.rename(os.path.join(self.wallet_secret, 'secret.subgrad.pub'), os.path.join(self.wallet_secret, '%s_secret.subgrad'%now_time_str))

      # 2.step regenerate new secret
      os.popen('ssh-keygen -t rsa -P "" -f %s/secret.subgrad -C ""' % self.wallet_secret)

  def rpc_get(self, **kwargs):
    request_url = 'http://%s:%d/api/get' % (self.server_ip, self.server_port)
    request_data = kwargs
    request_data.update({'public_key': self.public_key})
    try:
      result = requests.get(request_url, request_data)
      if result.status_code == 200 or result.status_code == 201:
        return json.loads(result.content)
      return None
    except:
      return None

  def rpc_put(self, **kwargs):
    try:
      ctx = get_global_context()
      request_url = 'http://%s:%d/api/%s' % (self.server_ip, self.server_port, kwargs['action'])
      request_data = kwargs
      request_data.update({'public_key': self.public_key,
                           'public_ip': ctx.public_ip,
                           'rpc_port': ctx.rpc_port,
                           'ssh_port': ctx.ssh_port})

      result = requests.post(request_url, request_data)

      if result.status_code == 200 or result.status_code == 201:
        return json.loads(result.content)
      return None
    except:
      return None

  def __getattr__(self, func_name):
    assert(func_name in ["get", "put"])

    def func(**kwargs):
      f = getattr(self, "rpc_%s" % func_name, None)
      return f(**kwargs)

    return func

# def get(**kwargs):
#   ctx = get_global_context()
#   blockchain_entry_ip = ctx.blockchain_entry_ip
#   blockchain_entry_port = ctx.blockchain_entry_port
#
#   request_url = 'http://%s:%d/api/get'%(blockchain_entry_ip, blockchain_entry_port)
#   request_data = kwargs
#   request_data.update({'public_key': ctx.wallet.public_key})
#   try:
#     result = requests.get(request_url, request_data)
#     if result.status_code == 200 or result.status_code == 201:
#       return json.loads(result.content)
#     return None
#   except:
#     return None
#
#
# def put(**kwargs):
#   ctx = get_global_context()
#   blockchain_entry_ip = ctx.blockchain_entry_ip
#   blockchain_entry_port = ctx.blockchain_entry_port
#
#   try:
#     request_url = 'http://%s:%d/api/%s'%(blockchain_entry_ip, blockchain_entry_port, kwargs['action'])
#     request_data = kwargs
#     request_data.update({'public_key': ctx.wallet.public_key, 'ip_address': ''})
#     result = requests.post(request_url,request_data)
#
#     if result.status_code == 200 or result.status_code == 201:
#       return json.loads(result.content)
#     return None
#   except:
#     return None