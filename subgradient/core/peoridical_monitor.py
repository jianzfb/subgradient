# -*- coding: UTF-8 -*-
# @Time : 2018/5/21
# @File : peoridical_monitor.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
# from subgradient.subgrad.chain import api
from subgradient.subgrad.chain.api import *
from subgradient.context import *
from subgradient import orm
from subgradient.core.cpu import *
from subgradient.core.gpu import *
from sqlalchemy import and_,or_
from subgradient.utils import *
from twisted.internet.task import LoopingCall
import logging
from traitlets.config import LoggingConfigurable
from traitlets import Integer
import copy


def monitor_order_status():
  # 0.step glocal context (get global varaibles)
  ctx = get_global_context()
  if ctx is None:
    return

  # 1.step check waiting off shelf stocks
  waiting_off_shelf_stocks = ctx.db.query(orm.Stock).filter(orm.Stock.status == 2).all()
  for stock in waiting_off_shelf_stocks:
    if stock.order is not None:
      if stock.order.status == -1 or stock.order.status == 3:
        stock.order = None
        ctx.db.commit()

    if stock.order is None:
      # 当前库存所对应的订单已经完成，修改库存状态
      stock.status = 4
  ctx.db.commit()

  # 2.step check abnormal and expire order, notify block chain and stop them
  exit_orders = ctx.db.query(orm.Order).filter(and_(or_(orm.Order.status == -1,
                                                        orm.Order.status == 3),
                                                    orm.Order.is_notify == False)).all()
  for order in exit_orders:
    # update order status
    if order.status == -1:
      chain_response = ctx.subgradient_chain_api.put(order_id=order.name,
                                                     action='update',
                                                     status='finish:fail:')
      if chain_response is not None:
        order.is_notify = True
        # try stop container
        if order.container_id != '':
          ctx.schedule.subgradient_server.stop(order)
    elif order.status == 3:
      chain_response = ctx.subgradient_chain_api.put(order_id=order.name,
                                                     action='update',
                                                     status='finish:success:')
      if chain_response is not None:
        order.is_notify = True
        # try stop container
        if order.container_id != '':
          ctx.schedule.subgradient_server.stop(order)
    # elif order.status == 0:
    #   ntp_now_time = now_time()
    #   if ntp_now_time is not None:
    #     if order.public_key != '':
    #       # 已经签约， 但是一直没有被用户登录过
    #       if ntp_now_time > order.launch_time + order.rental_time * 60 * 60:
    #         # 已经过期
    #         chain_response = chain.put(order_id=order.name,
    #                                    action='update',
    #                                    status='finish:success:')
    #         if chain_response is not None:
    #           order.status = 3
    #           order.is_notify = True

  ctx.db.commit()

  # 3.step check all status == 0,1,2 orders from block chain
  waiting_orders = ctx.db.query(orm.Order).filter(or_(orm.Order.status == 0,
                                                      orm.Order.status == 1,
                                                      orm.Order.status == 2)).all()
  ntp_now_time = ctx.ntp_time.time()
  for order in waiting_orders:
    order_content = ctx.subgradient_chain_api.get(order_id=order.name)
    if order_content is not None and order_content['status'] == 'sold' and order.status == 0:
        # check whether expire (process those orders which has been signed but not login here)
        launch_time = order_content['launch_time']
        rental_time = order_content['rental_time']
        if ntp_now_time is not None:
          if ntp_now_time > launch_time + rental_time * 60 * 60:
              chain_response = ctx.subgradient_chain_api.put(order_id=order.name,
                                                             action='update',
                                                             status='finish:success:')
              if chain_response is not None:
                order.status = 3
                order.is_notify = True

    if order_content is not None and order_content['status'] == 'fail':
      # now, we should republish new order
      order.status = -1
      order.is_notify = True

    if order_content is not None and order_content['status'] == 'stop':
      # now, we should republish new order
      # user could cancel his signed order in 10 minitues
      order.status = 3
      order.is_notify = True

  ctx.db.commit()

  # 4.step check processing order and their running status
  processing_orders = ctx.db.query(orm.Order).filter(or_(orm.Order.status == 1,
                                                         orm.Order.status == 2)).all()
  for order in processing_orders:
    if order.status == 1:
      # check container status for processing orders
      # 2.1.step check order expire time
      ntp_now_time = ctx.ntp_time.time()
      if ntp_now_time is None:
        logging.error('couldnt get time to judge rental expire')
        continue

      if ntp_now_time >= order.launch_time + order.rental_time * 60 * 60:
        order.status = 3          # stop and exit flag
        order.stock = None        # release stock
        ctx.schedule.subgradient_server.stop(order)  # stop container
        logging.info('stop expired order %s'%order.name)

        # notify chain
        result = ctx.subgradient_chain_api.put(order_id=order.name,
                                               action='update',
                                               status='finish:success:expire')
        if result is None:
          order.is_notify = False
          logging.error('couldnt update finish:success:expire flag of order %s on chain'%order.name)
        else:
          order.is_notify = True
        continue

      # 2.2.step check order server status
      try:
        response = ctx.schedule.subgradient_server.monitor(order)
        if response != 'running':
          #  unkown host error
          result = ctx.subgradient_chain_api.put(order_id=order.name, action='update', status='finish:fail:unkown')
          if result is None:
            order.is_notify = False
            logging.error('could update finish:fail: flag of order %s on chain'%order.name)
          else:
            order.is_notify = True

          order.status = -1
          order.stock = None
      except:
        logging.error('unkown error when monitor container %s'%order.container_id)

  ctx.db.commit()

  # 4.step finding resource occupy
  occupying_resource = {'cpu_num': 0,
                        'cpu_mem': 0,
                        'gpu_num': 0,
                        'gpu_mem': 0,
                        'disk': 0}
  waiting_or_onshelf_stocks = ctx.db.query(orm.Stock).filter(or_(orm.Stock.status == 3, orm.Stock.status == 2)).all()
  for stock in waiting_or_onshelf_stocks:
    occupying_resource['cpu_num'] = occupying_resource['cpu_num'] + stock.cpu_num
    occupying_resource['cpu_mem'] = occupying_resource['cpu_mem'] + stock.cpu_mem
    occupying_resource['gpu_num'] = occupying_resource['gpu_num'] + stock.gpu_num
    occupying_resource['gpu_mem'] = stock.gpu_mem
    occupying_resource['disk'] = occupying_resource['disk'] + stock.disk

  # 5.step check waiting onshelf stocks
  waiting_onshelf_stocks = ctx.db.query(orm.Stock).filter(orm.Stock.status == 1).all()
  total_free_cpu_num = ctx.schedule.schedule_cpu_quota
  total_free_cpu_mem = ctx.schedule.schedule_cpu_mem_quota

  total_free_gpu_num = 0
  total_free_gpu_mem = 0
  if ctx.schedule.gpu.is_gpu_ok:
    total_free_gpu_num = len(ctx.schedule.schedule_gpu_quota)
    total_free_gpu_mem = ctx.schedule.schedule_gpu_mem_quota

  for stock in waiting_onshelf_stocks:
    # 检查硬件资源是否允许上架
    cpu_num = stock.cpu_num
    cpu_mem = stock.cpu_mem
    gpu_num = stock.gpu_num
    gpu_mem = stock.gpu_mem
    disk_size = stock.disk

    is_ok = False
    if cpu_num <= total_free_cpu_num - occupying_resource['cpu_num'] and \
            cpu_mem <= total_free_cpu_mem -occupying_resource['cpu_mem']:
      if gpu_num <= total_free_gpu_num - occupying_resource['gpu_num'] and \
              gpu_mem <= total_free_gpu_mem:
        is_ok = True

    if is_ok:
      # update free record
      total_free_cpu_num -= cpu_num
      total_free_cpu_mem -= cpu_mem
      total_free_gpu_num -= gpu_num

      stock.status = 3

  # update db
  ctx.db.commit()

  # 4.step release new orders on chain
  onshelf_stocks = ctx.db.query(orm.Stock).filter(orm.Stock.status == 3).all()
  if len(onshelf_stocks) == 0:
    return

  base_images = ctx.db.query(orm.ImageRepository).all()
  if len(base_images) == 0:
    return

  # if len(onshelf_stocks) > 0:
  #   base_images = ctx.db.query(orm.ImageRepository).all()
  #   image_features = []
  #   for base_image in base_images:
  #     os_platform = base_image.os_platform
  #     os_version = base_image.os_version
  #     software_framework = copy.deepcopy(base_image.software_framework)
  #     if ' ' in software_framework:
  #       software_framework = software_framework.replace(' ', ';')
  #     elif ':' in software_framework:
  #       software_framework = software_framework.replace(':', ';')
  #     elif ',' in software_framework:
  #       software_framework = software_framework.replace(',', ';')
  #
  #     image_features.append('%s:%s:%s' % (os_platform, os_version, software_framework))
  #
  #   if len(image_features) == 0:
  #     return

  #  support_image_feature = ','.join(image_features)

  support_datasets = ctx.db.query(orm.Dataset).filter(orm.Dataset.status == 'support').all()
  support_dataset_feature = ','.join([dataset.dataset_name for dataset in support_datasets])

  for stock in onshelf_stocks:
    if stock.order is not None:
      if stock.order.status == -1 or stock.order.status == 3:
        stock.order = None
        ctx.db.commit()

    if stock.order is None:
      # 4.2.1.step order id
      order_id = unique_id()
      # 4.2.2.step release order on chain
      disk_read, disk_write = ctx.schedule.disk_speed
      net_upload, net_download = ctx.schedule.net_speed

      # 4.2.3.step config image feature
      image_features = []
      for base_image in base_images:
        os_platform = base_image.os_platform
        os_version = base_image.os_version
        software_framework = copy.deepcopy(base_image.software_framework)
        if ' ' in software_framework:
          software_framework = software_framework.replace(' ', ';')
        elif ':' in software_framework:
          software_framework = software_framework.replace(':', ';')
        elif ',' in software_framework:
          software_framework = software_framework.replace(',', ';')

        if stock.gpu_num > 0:
          if base_image.support_gpu:
            image_features.append('%s:%s:%s' % (os_platform, os_version, software_framework))
        else:
          if not base_image.support_gpu:
            image_features.append('%s:%s:%s' % (os_platform, os_version, software_framework))

      if len(image_features) == 0:
        continue

      support_image_feature = ','.join(image_features)

      # 4.2.4.step publish order on chain
      result = ctx.subgradient_chain_api.put(order_id=order_id,
                       cpu_model=stock.cpu_model,
                       cpu_num=stock.cpu_num,
                       cpu_mem=stock.cpu_mem,
                       gpu_model=stock.gpu_model,
                       gpu_num=stock.gpu_num,
                       gpu_mem=stock.gpu_mem,
                       disk_read=disk_read,
                       disk_write=disk_write,
                       net_upload=net_upload,
                       net_download=net_download,
                       max_rental_time=stock.max_rental_time,
                       min_rental_time=stock.min_rental_time,
                       fee=stock.fee,
                       charge_unit=stock.charge_unit,
                       disk=stock.disk,
                       feature=support_image_feature,
                       dataset_feature=support_dataset_feature,
                       action='new',
                       status='init::', )

      if result is None:
        logging.error('couldnt build a new order %s on chain'%order_id)
      else:
        # success release
        # 4.2.3.step submit order
        order = orm.Order(name=order_id, stock=stock, create_time=result['create_time'])
        ctx.db.add(order)
        ctx.db.commit()


class PeoridicalCalls(LoggingConfigurable):
  inverval = Integer(10, help='').tag(config=True)

  def __init__(self, **kwargs):
    super(PeoridicalCalls, self).__init__(**kwargs)

    self.callbakcs = []
    self.allways_callbacks = [monitor_order_status]

    self.loop_call = LoopingCall(self.run)
    self.loop_call.start(self.inverval)

  def register_always(self, peoridical_handler):
    pass

  def register(self, success_callback, fail_callback, trigger_func):
    self.callbakcs.append((success_callback, fail_callback, trigger_func))

  def run(self):
    # 1.step user customized callback
    remain_list = []
    for success_callback_func, fail_callback_func, trigger_func in self.callbakcs:
      trigger_flag = trigger_func()
      if trigger_flag == 1:
        # trigger success
        success_callback_func()
      elif trigger_flag == 0:
        # continue waiting
        remain_list.append((success_callback_func, fail_callback_func, trigger_func))
      else:
        # trigger fail
        fail_callback_func()

    self.callbakcs = remain_list

    # 2.step always callback
    for callback in self.allways_callbacks:
      callback()
