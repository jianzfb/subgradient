# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : app.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import atexit
import signal
from traitlets.config import Application, catch_config_error
from traitlets.traitlets import *
from traitlets import Dict
from traitlets import Bool
import subprocess
import subgradient
from subgradient import orm
from subgradient.core.container_monitor import *
from subgradient.core.operation_system import *
from subgradient.core.peoridical_monitor import *
from subgradient.core.schedule import *
from subgradient.core.image import *
from subgradient.interface.command import *
from subgradient.interface.cli import *
from subgradient.interface.ssh import *
from subgradient.interface.web import *
from multiprocessing import Process
from subgradient.network.lcx.lcx import *

import logging

aliases = {
  'log-level': 'Application.log_level',
  'f': 'Subgradient.config_file',
  'config': 'Subgradient.config_file',
}

flags = {
  'generate-config': ({'Subgradient': {'generate_config': True}},
    "generate default config file"),
  'debug': ({'Application': {'log_level': logging.DEBUG}},
            "set log level to logging.DEBUG (maximize logging output)"),
}

class Subgradient(Application):
  """An Application for starting a p2p computing server."""
  name = 'subgradient'
  version = subgradient.__version__

  description = """Start subgradient server in global"""

  aliases = Dict(aliases)
  flags = Dict(flags)

  config_file = Unicode('subgradient_config.py',
      help="The config file to load",
  ).tag(config=True)
  generate_config = Bool(False,
      help="Generate default config file",
  ).tag(config=True)
  log_file = Unicode('subgradient.log',
      help="""Send Subgradient's logs to this file.
      """
  ).tag(config=True)

  public_ip = Unicode('', help="public network ip address").tag(config=True)
  rpc_port = Integer(7080,help="listening rpc on this port",).tag(config=True)
  web_port = Integer(8000,help="listening http on this port").tag(config=True)
  ssh_port = Integer(9080, help="listening ssh on this port").tag(config=True)
  workspace = Unicode('', help='''subgradient workspace''').tag(config=True)
  token = Unicode('50b46931-d54c-4d03-8500-fe4ee123c818', help="").tag(config=True)
  support_ipfs = Bool(False, help="is support ipfs").tag(config=True)
  support_shootback = Bool(True, help="is support penetrate NAT").tag(config=True)

  classes = List([
    SubgradientServerAPI,
    SubgradientChainAPI,
    SubgradientSchedule,
    SubgradientNTP,
  ])

  examples = """

  generate default config file:

      subgradient --generate-config -f /etc/subgradient/subgradient_config.py
  """

  def __init__(self):
    super(Subgradient, self).__init__()
    self._subgradient_schedule = None
    self._image_manage = None
    self._ctx = None
    self._db = None

  @default('log_level')
  def _log_level_default(self):
    return logging.INFO

  @default('log_datefmt')
  def _log_datefmt_default(self):
    """Exclude date from default date format"""
    return "%Y-%m-%d %H:%M:%S"

  @default('log_format')
  def _log_format_default(self):
    """override default log format to include time"""
    return "%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s %(module)s:%(lineno)d %(message)s"

  @catch_config_error
  def initialize(self, *args, **kwargs):
    super(Subgradient, self).initialize(*args, **kwargs)
    if self.generate_config:
      self.write_config_file()
      return

    # 0.step load config file
    self.load_config_file(self.config_file)
    if self.workspace == '':
      self.worrkspace = os.environ.get('HOME', None)

    # initialize logging
    self.init_logging()

    # 1.step prepare all directorys managed by subgradient
    # workspace
    # dataset
    # shell
    # dockerfile
    # secret
    if not os.path.exists(os.path.join(self.workspace, 'dataset')):
      os.makedirs(os.path.join(self.workspace, 'dataset'))
    if not os.path.exists(os.path.join(self.workspace, 'secret')):
      os.makedirs(os.path.join(self.workspace, 'secret'))
    if not os.path.exists(os.path.join(self.workspace, 'shell')):
      os.makedirs(os.path.join(self.workspace, 'shell'))
    if not os.path.exists(os.path.join(self.workspace, 'workspace')):
      os.makedirs(os.path.join(self.workspace, 'workspace'))
    if not os.path.exists(os.path.join(self.workspace, 'dockerfile')):
      os.makedirs(os.path.join(self.workspace, 'dockerfile'))

    # 1.1.step launch ipfs daemon
    if self.support_ipfs:
      response = os.popen('ps aux | grep ipfs').read()
      lines = response.strip().split('\n')
      if len(lines) < 3:
        subprocess.Popen(['ipfs', 'daemon'])

    # 2.step initialize subgradient db
    self._db = scoped_session(orm.new_session_factory(url='sqlite:///subgradient.sqlite'))()

    # 3.step initialize subgradient resource schedule
    self._subgradient_schedule = SubgradientSchedule(db=self._db,
                                                     workspace=os.path.join(self.workspace, 'workspace'),
                                                     config=self.config)
    self._image_manage = ImageManage(db=self._db,
                                     workspace=self.workspace,
                                     config=self.config)
    self._ntp_time = SubgradientNTP(config=self.config)
    self._peoridical_calls = PeoridicalCalls(config=self.config)
    self._subgradient_server_api = SubgradientServerAPI(token=self.token,
                                                        config=self.config)
    self._subgradient_chain_api = SubgradientChainAPI(os.path.join(self.workspace,'secret'),
                                                      config=self.config)
    self._container_monitor = ContainerMonitor(config=self.config)

    # 4.step config global context
    self._ctx = Context(schedule=self._subgradient_schedule,
                        image_manage=self._image_manage,
                        db=self._db,
                        workspace=self.workspace,
                        subgradient_server_api=self._subgradient_server_api,
                        subgradient_chain_api=self._subgradient_chain_api,
                        ntp_time=self._ntp_time,
                        peoridical_calls = self._peoridical_calls,
                        public_ip=self.public_ip,
                        rpc_port=self.rpc_port,
                        ssh_port=self.ssh_port)

    # 5.step register on block chain
    public_key = self._subgradient_chain_api.public_key
    if public_key is None:
      self.log.info('genenrate RSA keys for subgradient')
      self._subgradient_chain_api.keygen()

    result = self._subgradient_server_api.register(public_key=public_key)
    if result is None:
      self.log.error('couldnt register on subgradient market')
      return
    if result['result'] == 'fail':
      self.log.error('couldnt register on subgradient market')
      return

    # 6.step clear up enviroment (abnormal orders)
    # we dont want any processing orders
    processing_orders = self._db.query(orm.Order).filter(or_(orm.Order.status == 1,
                                                             orm.Order.status == 2,
                                                             orm.Order.status == 0)).all()
    for order in processing_orders:
      self.log.info('clear residual order %s'%order.name)
      response = self._subgradient_schedule.subgradient_server.monitor(order)
      if response == 'running':
        self._subgradient_schedule.subgradient_server.stop(order)

      order.status = -1
      result = self._subgradient_chain_api.put(order_id=order.name,
                                               action='update',
                                               status='finish:fail:unkown')
      if result is None:
        order.is_notify = False
      else:
        order.is_notify = True

    self._db.commit()

    # 7.step register exit callback
    atexit.register(self.atexit)
    self.init_signal()

    # 8.step start listening
    # 8.1.step rpc
    reactor.listenTCP(int(self.rpc_port), Site(RPC()))

    # 8.2.step web
    reactor.listenTCP(int(self.web_port), Site(web_handlers()))

    # 8.3.step ssh
    reactor.listenTCP(int(self.ssh_port), ProxySSHFactory())

    # 8.4.step io
    stdio.StandardIO(CLI())

    # 9.step launch lcx (shootback nat)
    if self.support_shootback:
      process = Process(target=launch_shootback_proxy, args=('127.0.0.1:%d'%self.ssh_port, 'ssh'))
      process.daemon = True
      process.start()

      process = Process(target=launch_shootback_proxy, args=('127.0.0.1:%d'%self.rpc_port, 'rpc'))
      process.daemon = True
      process.start()

    # 10.step running forever
    reactor.run()

  def write_config_file(self):
    """Write our default config to a .py config file"""
    config_file_dir = os.path.dirname(os.path.abspath(self.config_file))
    if not os.path.isdir(config_file_dir):
        self.exit("{} does not exist. The destination directory must exist before generating config file.".format(
            config_file_dir,
        ))
    if os.path.exists(self.config_file):
      answer = ''
      def ask():
        prompt = "Overwrite %s with default config? [y/N]" % self.config_file
        try:
          return raw_input(prompt).lower() or 'n'
        except KeyboardInterrupt:
          print('') # empty line
          return 'n'
      answer = ask()
      while not answer.startswith(('y', 'n')):
        print("Please answer 'yes' or 'no'")
        answer = ask()
      if answer.startswith('n'):
        return

    config_text = self.generate_config_file()
    if isinstance(config_text, bytes):
      config_text = config_text.decode('utf8')
    print("Writing default config to: %s" % self.config_file)
    with open(self.config_file, mode='w') as f:
      f.write(config_text)

  def init_logging(self):
    # This prevents double log messages because tornado use a root logger that
    # self.log is a child of. The logging module dipatches log messages to a log
    # and all of its ancenstors until propagate is set to False.
    self.log.propagate = False

    if os.path.exists(self.log_file):
      os.remove(self.log_file)

    _formatter = self._log_formatter_cls(
        fmt=self.log_format,
        datefmt=self.log_datefmt,
    )

    log_handler = logging.FileHandler(self.log_file)
    log_handler.setFormatter(_formatter)
    self.log.addHandler(log_handler)

    # replace python navie logging root
    logging.root = self.log

  def cleanup(self):
    # close all processing orders and notify block chain
    # it's very bad, all money would be return
    self.log.info('start clear up enviroment')
    processing_orders = self._db.query(orm.Order).filter(or_(orm.Order.status == 1,
                                                             orm.Order.status == 2,
                                                             orm.Order.status == 0)).all()
    for order in processing_orders:
      response = self._subgradient_schedule.subgradient_server.monitor(order)
      if response == 'running':
        self._subgradient_schedule.subgradient_server.stop(order)

      order.status = -1
      result = self._subgradient_chain_api.put(order_id=order.name,
                                               action='update',
                                               status='finish:fail:unkown')
      if result is not None:
        order.is_notify = True
      else:
        order.is_notify = False

    self._db.commit()
    self.log.info('finish clear up enviroment')

  def init_signal(self):
    signal.signal(signal.SIGTERM, self.sigterm)

  def sigterm(self, signum, frame):
    self.log.critical("Received SIGTERM, shutting down")
    self.atexit()

  _atexit_ran = False
  def atexit(self):
    """atexit callback"""
    if self._atexit_ran:
      return
    self._atexit_ran = True
    # run the cleanup step (in a new loop, because the interrupted one is unclean)
    self.cleanup()

  @classmethod
  def launch_instance(cls, argv=None):
    self = cls.instance()
    self.initialize(argv)

main = Subgradient.launch_instance