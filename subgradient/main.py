# -*- coding: UTF-8 -*-
# @Time : 06/04/2018
# @File : main.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

from subgradient import app
from subgradient.appinstance import *

def main():
  subgradient_app = AppInstance('subgradient')
  app.main()
  subgradient_app.exit_app()


if __name__ == "__main__":
  main()