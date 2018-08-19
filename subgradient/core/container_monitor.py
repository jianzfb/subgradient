# -*- coding: UTF-8 -*-
# @Time : 2018/7/2
# @File : container_monitor.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import docker
from subgradient.context import *
from subgradient import orm
from subgradient.subgrad.ntptime.api import *
from twisted.internet.task import LoopingCall
from subgradient.utils import *
import json
# 测试磁盘写性能
# dd if=/dev/zero of=test.out bs=1M count=1024
# 测试磁盘读性能
# dd if=test.out of=/dev/null bs=1M count=1024


class ContainerMonitor(LoggingConfigurable):
  def __init__(self, **kwargs):
    super(ContainerMonitor, self).__init__(**kwargs)
    self.client = docker.from_env(version='auto')

    self.loop_call = LoopingCall(self.run)
    self.loop_call.start(10)

  @catch_error
  def run(self):
    # global context
    ctx = get_global_context()
    if ctx is None:
      return

    # all running orders
    running_orders = ctx.db.query(orm.Order).filter(orm.Order.status==1).all()
    container_snapshot = []
    for order in running_orders:
      if order.container_id != '':
        disk_write_quota = order.stock.disk_write

        # check container running status
        stats_generator = self.client.api.stats(container=order.container_id,decode=True)
        for stat in stats_generator:
          # memory usage  (G)
          memory_usage = stat['memory_stats']['usage'] / 1024.0 / 1024.0 / 1024.0
          memory_limit = stat['memory_stats']['limit'] / 1024.0 / 1024.0 / 1024.0

          # cpu usage (cpu %)
          cpu_delta = stat['cpu_stats']['cpu_usage']['total_usage'] - stat['precpu_stats']['cpu_usage']['total_usage']
          system_delta = stat['cpu_stats']['system_cpu_usage'] - (stat['precpu_stats']['system_cpu_usage'] if 'system_cpu_usage' in stat['precpu_stats'] else 0)
          cpu_usage = (float(cpu_delta)/float(system_delta) * len(stat['cpu_stats']['cpu_usage']['percpu_usage'])) * 100.0

          # net io (kb)
          net_i = 0.0
          net_o = 0.0
          net_stats = stat['networks']
          for k,v in net_stats.items():
            if k.startswith('eth'):
              net_i += float(v['rx_bytes'])
              net_o += float(v['tx_bytes'])
          net_i = net_i / 1024.0
          net_o = net_o / 1024.0

          # disk io (G)
          block_stats = stat['blkio_stats']['io_service_bytes_recursive']
          disk_read = 0.0
          disk_write = 0.0
          for block_stat in block_stats:
            if block_stat['op'] == 'Read':
              disk_read += block_stat['value']
            if block_stat['op'] == 'Write':
              disk_write += block_stat['value']
          disk_read = disk_read / 1024.0 / 1024.0 / 1024.0
          disk_write = disk_write / 1024.0 / 1024.0 / 1024.0

          # if disk_write > 1.2 * disk_write_quota:
          #   # exceed disk write quota 120%
          #   order.status = 3
          #   order.status_reason = 'EXCEED_DISK_QUOTA_ERROR'
          #   ctx.db.commit()

          # gpu status
          container_snapshot.append({'order': order.name,
                                     'container': order.container_id,
                                     'memory_usage': memory_usage,
                                     'memory_limit': memory_limit,
                                     'cpu_usage': cpu_usage,
                                     'net_i': net_i,
                                     'net_o': net_o,
                                     'disk_read': disk_read,
                                     'disk_write': disk_write})
          break

    if len(container_snapshot) > 0:
      # notify subgradient server all running containers snapshot
      ctx.subgradient_server_api.snapshot(snapshot=json.dumps(container_snapshot))
