# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : app.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import atexit
import signal
import subgradient
from traitlets.config import Application, catch_config_error
from traitlets import Unicode
from subgradient.core.schedule import *
from traitlets import Dict

aliases = {
  'log-level': 'Application.log_level',
  'f': 'Subgradient.config_file',
  'config': 'Subgradient.config_file',
}

flags = {
  'generate-config': ({'JupyterHub': {'generate_config': True}},
    "generate default config file"),
}

class Subgradient(Application):
  """An Application for starting a p2p computing server."""
  name = 'subgradient'
  version = subgradient.__version__

  description = """Start subgradient server in global
  """

  aliases = Dict(aliases)
  flags = Dict(flags)

  config_file = Unicode('subgradient_config.py',
      help="The config file to load",
  ).tag(config=True)

  examples = """

  generate default config file:

      subgradient --generate-config -f /etc/jupyterhub/subgradient_config.py
  """

  def __init__(self):
    self._subgradient_schedule = None

  @catch_config_error
  def initialize(self, *args, **kwargs):
    super().initialize(*args, **kwargs)

    self.load_config_file(self.config_file)
    self._subgradient_schedule = SubgradientSchedule(db=None, config=self.config)

    atexit.register(self.atexit)
    self.init_signal()

  def cleanup(self):
    print('clean up')
    pass

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

if __name__ == "__main__":
  main()