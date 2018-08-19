# -*- coding: UTF-8 -*-
# @Time : 2018/5/25
# @File : ssh.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

import base64, os, fcntl, tty, struct
from twisted.enterprise import adbapi
from twisted.cred import portal, checkers, credentials
from twisted.conch import error, avatar
from twisted.conch.unix import SSHSessionForUnixConchUser, UnixConchUser
from twisted.conch.checkers import SSHPublicKeyDatabase
from twisted.conch.ssh import factory, userauth, connection, keys, session
from twisted.internet import reactor, protocol, defer
from twisted.python import log
from twisted.internet import task
from zope.interface import implementer
from twisted.python import components, failure
from subgradient import orm
from subgradient.context import *
import sys
# from subgradient.subgrad.chain import api
from subgradient.subgrad.chain.api import *
import time
from subgradient.core.schedule import *
import socket
from datetime import datetime
from subgradient.utils import *
import copy

@implementer(checkers.ICredentialsChecker)
class PublicKeyCredentialsChecker(object):
  credentialInterfaces = (credentials.ISSHPrivateKey,)

  def __init__(self):
    # order db
    ctx = get_global_context()
    self.db = ctx.db
    self.ctx = ctx

  def requestAvatarId(self, credentials):
    # 1.step get order content on chain
    order_id = credentials.username
    order = self.db.query(orm.Order).filter(orm.Order.name == order_id).one_or_none()
    if order is None:
      return failure.Failure(error.ConchError('order dont exist'))

    if not credentials.signature:
      # user error (RSA fail)
      return failure.Failure(error.ValidPublicKey())

    if credentials.blob is None:
      return failure.Failure(error.ConchError('I dont recognize public key'))

    is_rsa_verification_ok = False
    if order.public_key == '':
      # 通过public key判断首次登陆
      ##############################################
      ####### read order complete info (chain) #####
      ##############################################
      order_content = self.ctx.subgradient_chain_api.get(order_id=order_id)
      # launch user customized infomation on order
      custom_public_key = order_content['public_key']           # public key of user on chain (after sign)
      order_status = order_content['status']                    # order status on chain       (after sign)
      os_platform = order_content['os_platform']                # user select os platform
      os_version = order_content['os_version']                  # user select os version
      software_framework = order_content['software_framework']  # user select basic software framework

      if custom_public_key == '' or order_status != 'sold':
        # system error, return all fee (manage on monitor_order_status())
        order.status = -1
        self.db.commit()
        return failure.Failure(error.ConchError('order has not been signed'))

      # rsa verification
      if credentials.blob != base64.decodestring(custom_public_key.split(" ")[1]):
        # user error (RSA fail)
        return failure.Failure(error.ConchError('I dont recognize public key'))
      user_key = keys.Key.fromString(data=custom_public_key)
      if not user_key.verify(credentials.signature, credentials.sigData):
        return failure.Failure('Incorrect signature')
      is_rsa_verification_ok = True

      support_gpu = False
      if order.stock.gpu_num > 0:
        support_gpu = True

      if ',' in software_framework:
        software_framework = software_framework.replace(',', ';')
      base_image = self.db.query(orm.ImageRepository).filter(and_(orm.ImageRepository.os_platform == os_platform,
                                                                  orm.ImageRepository.os_version == os_version,
                                                                  orm.ImageRepository.software_framework == software_framework,
                                                                  orm.ImageRepository.support_gpu == support_gpu)).one_or_none()
      if base_image is None:
        # system error, return all fee (manage on monitor_order_status())
        order.status = -1
        self.db.commit()
        return failure.Failure(error.ConchError('base image dont exist'))

      # fill missing info on order (from user)
      order.platform_config = {"os_platform": os_platform,
                               'os_version': os_version,
                               'software_framework': software_framework}
      order.running_config = {'ENV': {'IPFS_HOST': host_ip()}}
      order.public_key  = custom_public_key                                                             # user name
      order.leaseholder = custom_public_key                                                             # user name
      order.image_name = '%s/%s'%(order_content['os_platform'].lower(),
                                  time.strftime('%Y%m%d%H%M%S%f',
                                                time.localtime(time.time())))   # custom image name
      order.launch_time = float(order_content['launch_time'])     # 签约时间
      order.rental_time = float(order_content['rental_time'])     # 租赁时间（小时）
      order.punish = order_content['punish']
      self.db.commit()
    else:
      if order.status not in [0, 1, 2]:
        return failure.Failure(error.ConchError('invalid resource order'))

      if order.status == 2:
        return failure.Failure(error.ConchError('waiting to schedule'))

    # here order.status == 0 or order.status == 1
    # check whether order has arrived rental time
    # (if order.status != 1, container should already exited)
    ntp_now_time = self.ctx.ntp_time.time()
    if ntp_now_time is not None:
      if ntp_now_time > order.launch_time + order.rental_time * 60 * 60:
        # expire time
        order.status = 3
        self.db.commit()
        return failure.Failure(error.ConchError('order server has been stop'))

    # 2.step verificatino
    if not is_rsa_verification_ok:
      if credentials.blob != base64.decodestring(order.public_key.split(" ")[1]):
        # user error (RSA fail)
        return failure.Failure(error.ConchError('I dont recognize public key'))

      user_key = keys.Key.fromString(data=order.public_key)
      if user_key.verify(credentials.signature, credentials.sigData):
        return credentials.username
      else:
        # user error (RSA fail)
        print('signature check failed')
        return failure.Failure('Incorrect signature')

    return credentials.username


class ProxySSHUser(avatar.ConchUser):
  def __init__(self, username):
    avatar.ConchUser.__init__(self)
    self.username = username
    self.channelLookup.update({'session': session.SSHSession})

  def getUserGroupId(self):
    return None, None


@implementer(portal.IRealm)
class ProxySSHRealm:
  def requestAvatar(self, avatarId, mind, *interfaces):
    return interfaces[0], ProxySSHUser(avatarId), lambda: None


class ProxySSHSession(SSHSessionForUnixConchUser):
  def _launch_ssh_server(self, order):
    # inner function (get valid port)
    def _is_open(check_ip, port):
      s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      try:
        s.connect((check_ip, int(port)))
        s.shutdown(2)
        return True
      except:
        return False

    # 1.step global context (get global variables)
    ctx = get_global_context()

    # 2.step launch order server container
    # assign a random ssh port
    using_ssh_port_offset = 7000
    while True:
      has_it = ctx.db.query(orm.Order).filter(and_(orm.Order.ssh_port == using_ssh_port_offset,
                                                  or_(orm.Order.status == 1,
                                                      orm.Order.status == 2))).one_or_none()
      if has_it is not None:
        using_ssh_port_offset += 1
      else:
        if not _is_open('127.0.0.1', using_ssh_port_offset):
          break

      using_ssh_port_offset += 1

    order.ssh_port = using_ssh_port_offset
    ctx.db.commit()

    # schedule server
    running_config = copy.deepcopy(order.running_config)
    running_config.update({'cmd': '/usr/sbin/sshd -D', 'port_bindings': {22: order.ssh_port}})
    platform_config = order.platform_config
    result = ctx.schedule.schedule({'running_config':running_config,
                                    'platform_config':platform_config,
                                    'order': order})
    return result


  def openShell(self, proto):
    # 0.step global context (get global variables)
    ctx = get_global_context()

    # 1.step check running environment
    order_id = self.avatar.username
    order = ctx.db.query(orm.Order).filter(orm.Order.name == order_id).one_or_none()
    if order.container_id == '':
      # try start server
      response = self._launch_ssh_server(order)
      if response['result'] == 'fail':
        # system error
        order.status = -1
        ctx.db.commit()
        return error.ConchError('ssh server error')

    # if not is_first_launch:
    #   running_status = ctx.schedule.subgradient_server.monitor(order)
    #   if running_status != 'running':
    #     # try restart server
    #     response = self._launch_ssh_server(order)
    #     if response['result'] == 'fail':
    #       return error.ConchError('ssh server error')

    # 2.step build ssh connect
    uid, gid = self.avatar.getUserGroupId()
    command = "/usr/bin/ssh"
    args = ["ssh", "-p %d"%order.ssh_port, "root@127.0.0.1"]
    self.pty = reactor.spawnProcess(proto, command, args, {}, "/", uid, gid, usePTY=self.ptyTuple)
    # 画面幅を調整
    # fcntl.ioctl(self.pty.fileno(), tty.TIOCSWINSZ, struct.pack('4H', *self.winSize))
    self.avatar.conn.transport.transport.setTcpNoDelay(1)

  def closed(self):
    # close ssh session
    # super(ProxySSHSession, self).closed()

    # # commit image update
    # order_id = self.avatar.username
    # # global context (get global variables)
    # ctx = get_global_context()
    # # update custom image
    # order = ctx.db.query(orm.Order).filter(orm.Order.name == order_id).one_or_none()
    # client = docker.from_env(version='auto')
    # client.containers.get(order.container_id).commit(order.image_name)
    pass


class ProxySSHFactory(factory.SSHFactory):
  home_dir = os.environ['HOME']
  with open(os.path.join(home_dir, '.ssh', 'id_rsa')) as privateBlobFile:
    privateBlob = privateBlobFile.read()
    privateKey = keys.Key.fromString(data=privateBlob)

  with open(os.path.join(home_dir, '.ssh', 'id_rsa.pub')) as publicBlobFile:
    publicBlob = publicBlobFile.read()
    publicKey = keys.Key.fromString(data=publicBlob)

  publicKeys = {'ssh-rsa': publicKey}
  privateKeys = {'ssh-rsa': privateKey}

  def __init__(self):
    sw = portal.Portal(ProxySSHRealm())
    components.registerAdapter(ProxySSHSession, ProxySSHUser, session.ISession)
    sw.registerChecker(PublicKeyCredentialsChecker())
    ProxySSHFactory.portal = sw
