# -*- coding: UTF-8 -*-
# @Time : 2018/8/15
# @File : peoridical_ping.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

from traitlets.config import LoggingConfigurable
from twisted.internet.task import LoopingCall
from subgradient.utils import *
from subgradient.context import *
from traitlets import Integer
from subgradient.subgrad.server import api
from subgradient.subgrad.chain import api
from subgradient import orm
from sqlalchemy import and_,or_


class PingMonitor(LoggingConfigurable):
  inverval = Integer(60, help='').tag(config=True)

  def __init__(self, **kwargs):
    super(PingMonitor, self).__init__(**kwargs)
    self.loop_call = LoopingCall(self.run)
    self.loop_call.start(self.inverval)

  @catch_error
  def run(self):
    # global context
    ctx = get_global_context()
    if ctx is None:
      return

    # ping server, Im on line
    orders = ctx.db.query(orm.Order).filter(or_(orm.Order.status == 0,
                                                orm.Order.status == 1,
                                                orm.Order.status == 2)).all()
    if len(orders) > 0:
      order_name = ','.join([order.name for order in orders])
      ctx.subgradient_chain_api.ping(order_id=order_name)