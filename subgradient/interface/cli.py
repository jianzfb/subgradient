# -*- coding: UTF-8 -*-
# @Time : 2018/5/17
# @File : cli.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from twisted.internet import stdio
from twisted.protocols import basic
from os import linesep
from traitlets.config import LoggingConfigurable
from subgradient.context import *
from subgradient import orm
import getopt
import time
import os
import uuid
import shutil

class BaseCLI(LoggingConfigurable):
  def __init__(self, **kwargs):
    super(BaseCLI, self).__init__(**kwargs)

  def process(self, funcname, **kwargs):
    f = getattr(self, "cli_%s" % funcname, None)
    if f is None or not callable(f):
      msgargs = (self.__class__.__name__, funcname)
      self.log.error("%s has no callable method cli_%s; ignoring request", *msgargs)
      return 'INVALID COMMAND or PARAMETER'

    try:
      cli_response = f(**kwargs)
      return cli_response
    except:
      return 'COMMAND ERROR'

class SubgradientCLI(BaseCLI):
  def cli_stock(self, **kwargs):
    # 0.step global context (get global varaiables)
    ctx = get_global_context()

    # 1.step stocks
    current_stocks = ['%10s %10s %10s %10s %10s %10s %10s %10s %15s %15s %10s'%('ID',
                                                                                'CPU',
                                                                                'MEM',
                                                                                'GPU',
                                                                                'GPU_MEM',
                                                                                'DISK',
                                                                                'FEE',
                                                                                'CHARGE_UNIT',
                                                                                'MAX_RENTAL(H)',
                                                                                'MIN_RENTAL(H)',
                                                                                'STATUS')]
    stocks = ctx.db.query(orm.Stock).all()
    # charge_unit = {'s': '秒', 'm': '分钟','h': '小时', 'd': '天', 'w':'周'}
    for stock_i, stock in enumerate(stocks):
      stock_status = ''
      if stock.status == 1:
        stock_status = 'waiting on-shelf'
      elif stock.status == 2:
        stock_status = 'waiting off-shelf'
      elif stock.status == 3:
        stock_status = 'on-shelf'
      else:
        stock_status = 'off-shelf'

      max_rental_time = '%.2f'%stock.max_rental_time
      min_rental_time = '%.2f'%stock.min_rental_time
      current_stocks.append('%10d %10d %10d %10d %10d %10d %10.2f %10s %15.2f %15.2f %10s'%(int(stock.id),
                                                                                      int(stock.cpu_num),
                                                                                      int(stock.cpu_mem),
                                                                                      int(stock.gpu_num),
                                                                                      int(stock.gpu_mem),
                                                                                      int(stock.disk),
                                                                                      stock.fee,
                                                                                      stock.charge_unit,
                                                                                      float(max_rental_time),
                                                                                      float(min_rental_time),
                                                                                      stock_status))

    current_stocks_str = '\n'.join(current_stocks)
    return current_stocks_str

  def cli_addstock(self, **kwargs):
    # 0.step global context (get global variable)
    ctx = get_global_context()
    total_cpu_num = len(ctx.schedule.cpu.cpu_model_name())
    total_cpu_mem = ctx.schedule.cpu.cpu_total_mem()

    total_gpu_num = 0
    total_gpu_mem = 0
    if ctx.schedule.gpu.is_gpu_ok:
      total_gpu_num = len(ctx.schedule.gpu.gpu_model_name())
      total_gpu_mem = ctx.schedule.gpu.gpu_total_mem(0)

    # 1.step check parameters
    cpu_num = kwargs.get('cpu_num', None)
    if cpu_num is None:
      return 'MUST SET cpu_num'
    cpu_num = int(cpu_num)
    if cpu_num > total_cpu_num:
      return 'cpu_num is larger than physical cores'

    cpu_mem = kwargs.get('cpu_mem', None)
    if cpu_mem is None:
      return 'MUST SET cpu_mem'
    cpu_mem = int(cpu_mem)
    if cpu_mem > total_cpu_mem:
      return 'cpu_mem is larger than physical memory'

    gpu_num = kwargs.get('gpu_num', None)
    if gpu_num is None:
      return 'MUST SET gpu_num'
    gpu_num = int(gpu_num)
    if gpu_num > total_gpu_num:
      return 'gpu_num is larger than physical GPU cores'

    gpu_mem = kwargs.get('gpu_mem', None)
    if gpu_mem is None:
      return 'MUST SET gpu_mem'
    gpu_mem = int(gpu_mem)
    if gpu_mem > total_gpu_mem:
      return 'gpu_mem is larger than physical GPU memory'

    disk_size = kwargs.get('disk_size', None)
    if disk_size is None:
      return 'MUST SET disk_size'
    disk_size = int(disk_size)

    min_rental_time = kwargs.get('min_rental_time', None)
    if min_rental_time is None:
      return 'MUST SET min_rental_time'
    min_rental_time = float(min_rental_time)

    max_rental_time = kwargs.get('max_rental_time', None)
    if max_rental_time is None:
      return 'MUST SET max_rental_time'
    max_rental_time = float(max_rental_time)

    if max_rental_time < min_rental_time:
      return 'max_rental_time must be larger than min_rental_time'

    fee = kwargs.get('fee', None)
    if fee is None:
      return 'MUST SET fee'
    fee = float(fee)

    # 2.step add db
    cpu_model = ctx.schedule.cpu.cpu_model_name(0)
    gpu_model = ''
    if ctx.schedule.gpu.is_gpu_ok:
      gpu_model = ctx.schedule.gpu.gpu_model_name(0)

    stock = orm.Stock(name='',
                      cpu_model=cpu_model,
                      cpu_num=cpu_num,
                      cpu_mem=cpu_mem,
                      gpu_model=gpu_model,
                      gpu_num=gpu_num,
                      gpu_mem=gpu_mem,
                      disk=disk_size,
                      fee=fee,
                      charge_unit='h',
                      max_rental_time=max_rental_time,
                      min_rental_time=min_rental_time,
                      status=1)
    ctx.db.add(stock)
    ctx.db.commit()
    return 'SUCCESS to SUBMIT'

  def cli_updatestock(self, **kwargs):
    # 0.step global context (get global varaiables)
    ctx = get_global_context()

    # 1.step check parameter
    stock_id = kwargs.get('stock_id', None)
    if stock_id is None:
      return 'MUST SET stock_id'
    stock_id = int(stock_id)

    stock = ctx.db.query(orm.Stock).filter(orm.Stock.id == stock_id).one_or_none()
    if stock is None:
      return 'DONT EXIST %d stock'%stock_id

    status = kwargs.get('stock_status', None)
    if status is None:
      return 'MUST SET stock_status'

    if status != 'on-shelf' and status != 'off-shelf':
      return 'PARAMETER "stock_status" is only allowed "on-shelf" or "off-shelf"'

    if stock.status == 1 or stock.status == 2:
      return 'stock status is frozen, please wait a moment'

    if status == 'on-shelf' and stock.status == 3:
      return 'SUCCESS to CHANGE'
    elif status == 'off-shelf' and stock.status == 4:
      return 'SUCCESS to CHANGE'

    if status == 'on-shelf':
      stock.status = 3
      ctx.db.commit()
    else:
      stock.status = 4
      ctx.db.commit()

    return 'SUCCESS to CHANGE'


  def cli_image(self, **kwargs):
    # 0.step global context (get global varaiables)
    ctx = get_global_context()

    # 1.step get all base images
    base_images = ctx.db.query(orm.ImageRepository).filter(orm.ImageRepository.is_base == True).all()
    base_image_info = ['%5s %10s %10s %20s %20s %15s %5s %30s %30s %10s'%('INDEX',
                                                                           'OS',
                                                                           'OS_VERSION',
                                                                           'SOFTWARE',
                                                                           'IMAGE',
                                                                           'DOCKERFILE',
                                                                           'GPU',
                                                                           'START',
                                                                           'STOP',
                                                                           'STATUS')]
    for base_image_index, base_image in enumerate(base_images):
      base_image_info.append('%5d %10s %10s %20s %20s %15s %5s %30s %30s %10s'%(base_image_index,
                                                                                base_image.os_platform,
                                                                                base_image.os_version,
                                                                                base_image.software_framework,
                                                                                base_image.image_name,
                                                                                base_image.dockerfile.split('/')[-1],
                                                                                'yes' if base_image.support_gpu else 'no',
                                                                                time.strftime('%Y-%m-%d %H:%M:%S',
                                                                                              time.localtime(
                                                                                                base_image.building_start)),
                                                                                time.strftime('%Y-%m-%d %H:%M:%S',
                                                                                              time.localtime(
                                                                                                base_image.building_start)) if base_image.building_finish else '-',
                                                                                'finish' if base_image.building_finish else 'processing'))
    base_image_info_str = '\n'.join(base_image_info)
    return base_image_info_str

  def cli_hardware(self, **kwargs):
    # 0.step global context (get global variables)
    ctx = get_global_context()

    # 1.step get hardware list
    cpu_models = ctx.schedule.cpu.cpu_model_name()
    cpu_mem = ctx.schedule.cpu.cpu_total_mem()

    gpu_models = []
    gpu_mem = [0]
    if ctx.schedule.gpu.is_gpu_ok:
      gpu_models = ctx.schedule.gpu.gpu_model_name()
      gpu_mem = ctx.schedule.gpu.gpu_total_mem()

    hardware_info = ['%10s %10s %10s %10s'%('CPU', 'MEM', 'GPU', 'GPU_MEM')]
    hardware_info.append('%10d %10d %10d %10d'%(len(cpu_models), cpu_mem, len(gpu_models), gpu_mem[0]))

    hardware_info_str = '\n'.join(hardware_info)
    return hardware_info_str

  def cli_money(self, **kwargs):
    # 0.step global context (get global varaibles)
    ctx =  get_global_context()

    # 1.step get money
    my_money = ctx.subgradient_chain_api.money()

    money_info = ['%20s %20s'%('MONEY', 'FROZEN_MONEY')]
    money_info.append('%20.2f %20.2f'%(my_money['money'], my_money['frozen_money']))
    money_info_str = '\n'.join(money_info)
    return money_info_str



class CLI(basic.LineReceiver):
  delimiter = linesep.encode("ascii")

  def __init__(self):
    self.cli = SubgradientCLI()

  def connectionMade(self):
    self.transport.write(b'>>> ')

  def lineReceived(self, line):
    # 1.step parse line content (cmd ....)
    key_terms = line.split(' ')
    cmd = key_terms[0]
    params = key_terms[1:]

    try:
      kv_args, args = getopt.getopt(params, "",["cpu_num=",
                                                "cpu_mem=",
                                                "gpu_num=",
                                                "gpu_mem=",
                                                "disk_size=",
                                                "fee=",
                                                "min_rental_time=",
                                                "max_rental_time=",
                                                "image_name=",
                                                "os_platform=",
                                                "os_version=",
                                                "software_platform=",
                                                "support_gpu=",
                                                "dockerfile=",
                                                "stock_id=",
                                                "stock_status=",])
      kwargs = {}
      for kv in kv_args:
        kwargs[kv[0].replace('--','')] = kv[1]

      # 2.step process command
      result = self.cli.process(cmd, **kwargs)

      # 3.step return result
      self.sendLine(result.encode('utf-8'))
      self.transport.write(b'>>> ')
    except:
      # 3.step return result
      self.sendLine(b'BAD PARAMETER')
      self.transport.write(b'>>> ')
