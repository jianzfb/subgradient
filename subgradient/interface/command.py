# -*- coding: UTF-8 -*-
# @Time : 2018/6/6
# @File : command.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from twisted.web.resource import Resource,NoResource
from subgradient.context import *
from subgradient import orm
from sqlalchemy import and_,or_
import os
import json
# from subgradient.subgrad.chain import api
from subgradient.subgrad.chain.api import *
import Crypto
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15
from Crypto.PublicKey import RSA
from subgradient.utils import *
import functools


class BaseRPC(Resource):
  def render_POST(self, request):
    # prase request
    kwargs = {}
    for k, v in request.args.items():
      kwargs[k] = v[0]

    result = self.callback(**kwargs)
    return json.dumps(result).encode('utf-8')

  def callback(self, **kwargs):
    return {}


class AuthorizeRPC(BaseRPC):
  def rsa_check(self, verify_content, signature, public_key):
    is_ok = False
    key = RSA.import_key(public_key.strip())
    h = SHA256.new(verify_content.encode('utf-8'))
    try:
      pkcs1_15.new(key).verify(h, signature)
      is_ok = True
    except (ValueError, TypeError):
      is_ok = False

    return is_ok

  def callback(self, order_id, secret, signature):
    # 0.step global context (get global variables)
    ctx = get_global_context()

    # 1.step check signature consistent
    order = ctx.db.query(orm.Order).filter(orm.Order.name == order_id).one_or_none()
    if order is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ORDER'}

    if order.status not in [0, 1, 2]:
      return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_OR_TERMINATE_ERROR'}

    is_rsa_verification_ok = False
    if order.public_key == '':
      # 用户签约后的首次授权
      order_content = ctx.subgradient_chain_api.get(order_id=order_id)
      custom_public_key = order_content['public_key']
      order_status = order_content['status']                    # order status on chain       (after sign)
      os_platform = order_content['os_platform']                # user select os platform
      os_version = order_content['os_version']                  # user select os version
      software_framework = order_content['software_framework']  # user select basic software framework

      if custom_public_key == '' or order_status != 'sold':
        return {'authorize': 'fail', 'reason': 'NO_SIGNED_ORDER'}

      # RSA verification
      is_rsa_verification_ok = self.rsa_check('%s.%s' % (secret, order_id), signature, custom_public_key)
      if not is_rsa_verification_ok:
        return {'authorize': 'fail', 'reason': 'SIGNATURE_CONSISTENT_ERROR'}

      base_image = None
      if os_platform != '' and os_version != '' and software_framework != '':
        base_image = ctx.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                    orm.ImageRepository.os_version == os_version,
                                                                    orm.ImageRepository.software_framework == software_framework)).first()
      elif os_platform != '' and os_version != '':
        base_image = ctx.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                    orm.ImageRepository.os_version == os_version)).first()
      elif os_platform != '' and software_framework != '':
        base_image = ctx.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                    orm.ImageRepository.software_framework == software_framework)).first()
      elif os_platform != '':
        base_image = ctx.db.query(orm.ImageRepository).filter(orm.ImageRepository.os_platform == os_platform).first()
      elif software_framework != '':
        base_image = ctx.db.query(orm.ImageRepository).filter(orm.ImageRepository.software_framework == software_framework).first()
      elif os_platform == '' and os_version == '' and software_framework == '':
        base_image = ctx.db.query(orm.ImageRepository).all()[0]

      if base_image is None:
        # system error
        order.status = -1
        ctx.db.commit()
        return {'authorize': 'fail', 'reason': 'NO_IMAGE_ORDER'}

      # fill order missing info
      order.platform_config = {"os_platform": os_platform,
                               'os_version': os_version,
                               'software_framework': software_framework}

      order.running_config = {}
      order.public_key  = custom_public_key                                                             # user name
      order.leaseholder = custom_public_key                                                             # user name
      order.image_name = '%s/%s'%(order_content['os_platform'].lower(),
                                  time.strftime('%Y%m%d%H%M%S%f',
                                                time.localtime(time.time())))                           # image name
      order.launch_time = float(order_content['launch_time'])
      order.rental_time = float(order_content['rental_time'])
      order.create_time = float(order_content['create_time'])
      order.punish = order_content['punish']
      ctx.db.commit()

    # rsa verification
    if not is_rsa_verification_ok:
      is_rsa_verification_ok = self.rsa_check('%s.%s'%(secret, order_id), signature, order.public_key.strip())
      if not is_rsa_verification_ok:
        return {'authorize': 'fail', 'reason': 'SIGNATURE_CONSISTENT_ERROR'}

    # 2.step check > rental time
    ntp_now_time = ctx.ntp_time.time()
    if ntp_now_time is not None:
      if ntp_now_time > order.launch_time + order.rental_time * 60 * 60:
        order.status = 3
        ctx.db.commit()
        return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_ERROR'}

    # 3.step generate access token
    order.token_expire_time = time.time() + 24 * 60 * 60      # token will be expire after 1 day
    access_token = order.new_api_token()
    order.is_token_refresh = False
    ctx.db.commit()

    return {'authorize': 'success',
            'access_token': access_token,
            'expire_time': order.token_expire_time,
            'launch_time': order.launch_time,
            'rental_time': order.rental_time * 60 * 60}


class RefreshRPC(BaseRPC):
  def callback(self, access_token):
    # refresh call, must be only once
    # 0.step global context (get global variables)
    ctx = get_global_context()

    # 1.step check access token
    token = orm.APIToken.find(ctx.db, access_token)
    if token is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ACCESS_TOKEN_ERROR'}
    if token.order is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ACCESS_TOKEN_ERROR'}

    order = token.order
    if order.status not in [0, 1, 2]:
      return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_OR_TERMINATE_ERROR'}

    ntp_now_time = ctx.ntp_time.time()
    if ntp_now_time is not None:
      if ntp_now_time > order.launch_time + order.rental_time * 60 * 60:
        order.status = 3
        ctx.db.commit()
        return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_ERROR'}

    if order.is_token_refresh:
      return {'authorize': 'fail', 'reason': 'REAUTHORIZE_ERROR'}

    refresh_access_token = token.order.new_api_token()
    token.order.token_expire_time = time.time() + 24 * 60 * 60
    token.order.is_token_refresh = True
    ctx.db.commit()

    return {'authorize': 'success',
            'access_token': access_token,
            'refresh_access_token': refresh_access_token,
            'expire_time': order.token_expire_time}


class LaunchRPC(BaseRPC):
  def _is_open(self, check_ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
      s.connect((check_ip, int(port)))
      s.shutdown(2)
      return True
    except:
      return False

  def callback(self, access_token, cmd=None, code_address=None, code_address_code=None):
    # 0.step global context (get global variables)
    ctx = get_global_context()

    # 1.step check access token is valid
    token = orm.APIToken.find(ctx.db, access_token)
    if token is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ACCESS_TOKEN_ERROR'}
    if token.order is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ACCESS_TOKEN_ERROR'}

    order = token.order
    if order.status not in [0, 1, 2]:
      return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_OR_TERMINATE_ERROR'}

    if order.status in [1, 2]:
      return {'authorize': 'success', 'result':'fail', 'reason': 'RELAUNCH_ERROR'}

    if order.token_expire_time <= time.time():
      return {'authorize': 'fail', 'reason': 'EXPIRE_ACCESS_TOKEN_ERROR'}

    ntp_now_time = ctx.ntp_time.time()
    if ntp_now_time is not None:
      if ntp_now_time > order.launch_time + order.rental_time * 60 * 60:
        order.status = 3
        ctx.db.commit()
        return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_ERROR'}

    # 2.step start container may spend much time, move to defered object
    # run in independent thread
    using_ssh_port_offset = 7000
    while True:
      has_it = ctx.db.query(orm.Order).filter(and_(orm.Order.ssh_port == using_ssh_port_offset,
                                                  or_(orm.Order.status == 1,
                                                      orm.Order.status == 2))).one_or_none()
      if has_it is not None:
        using_ssh_port_offset += 1
      else:
        if not self._is_open('127.0.0.1', using_ssh_port_offset):
          break

      using_ssh_port_offset += 1

    order.ssh_port = using_ssh_port_offset
    order.status = 2    # schedule status
    ctx.db.commit()

    # 3.step task schedule
    # 3.1.step independent thread
    ctx.schedule.schedule_download_files(order.name, code_address, code_address_code)

    # 3.2.step register peoridicallcalls
    running_config = {'cmd': cmd,
                      'code_address': code_address,
                      'port_bindings': {22: order.ssh_port},
                      'ENV': {'IPFS_HOST': host_ip()}}

    def _trigger_func():
      if os.path.exists(os.path.join(ctx.schedule.workspace, order.name, 'download.success')):
        # continue
        return 1
      elif os.path.exists(os.path.join(ctx.schedule.workspace, order.name, 'download.fail')):
        # exit
        return -1
      else:
        # waiting
        return 0

    schedule_info = {'order': order,
                     'running_config': running_config,
                     'platform_config': order.platform_config}
    ctx.peoridical_calls.register(functools.partial(ctx.schedule.schedule, schedule_info),
                                  functools.partial(ctx.schedule.dummy_schedule, schedule_info),
                                  _trigger_func)

    return {'authorize': 'success',
            'result': 'NOT_DONE_YET'}


class StatusRPC(BaseRPC):
  def callback(self, access_token):
    # 0.step global context (get global variables)
    ctx = get_global_context()

    # 1.step check access token is valid
    token = orm.APIToken.find(ctx.db, access_token)
    if token is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ACCESS_TOKEN_ERROR'}
    if token.order is None:
      return {'authorize': 'fail', 'reason': 'INVALID_ACCESS_TOKEN_ERROR'}

    order = token.order
    if order.status not in [1, 2]:
      return {'authorize': 'fail', 'reason': 'EXPIRE_RENTAL_OR_TERMINATE_ERROR'}

    if order.token_expire_time <= time.time():
      return {'authorize': 'fail',
              'reason': 'EXPIRE_ACCESS_TOKEN_ERROR'}

    ntp_now_time = ctx.ntp_time.time()
    if ntp_now_time is not None:
      if ntp_now_time > order.launch_time + order.rental_time * 60 * 60:
        order.status = 3
        ctx.db.commit()
        return {'authorize': 'fail',
                'reason': 'EXPIRE_RENTAL_ERROR'}

    # 1.step look up server status
    if order.status == 2:
      return {'authorize': 'success', 'result': 'schedule'}
    else:
      res = ctx.schedule.subgradient_server.monitor(order=order)
      return {'authorize': 'success', 'result': res}


class PingRPC(BaseRPC):
  def callback(self, **kwargs):
    return {'result': 'valid'}


class OrderRPC(BaseRPC):
  def callback(self, **kwargs):
    order_id = kwargs.get('order_id', 'None')
    if order_id is None:
      return {'result': 'invalid'}

    ctx = get_global_context()
    order = ctx.db.query(orm.Order).filter(and_(orm.Order.name==order_id,
                                                orm.Order.status==0)).one_or_none()
    if order is None:
      return {'result': 'invalid'}

    return {'result': 'valid'}


class RPC(Resource):
  def getChild(self, path, request):
    path_str = path.decode()
    keys = os.path.normpath(path_str).split('/')

    class_name = '%sRPC'%keys[0].capitalize()
    class_obj = globals().get(class_name, None)
    if class_obj is None:
      return NoResource()
    else:
      return class_obj()
