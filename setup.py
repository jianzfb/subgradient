# -*- coding: UTF-8 -*-
# @Time : 29/03/2018
# @File : setup.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from setuptools import setup, find_packages

setup(
  name='subgradient',
  version='0.1.0',
  description=('share global computing power'),
  long_description=open('README.rst').read(),
  author='jian',
  author_email='jian@mltalker.com',
  maintainer='jian',
  maintainer_email='jian@mltalker.com',
  license='BSD License',
  packages=find_packages(),
  platforms=["all"],
  install_requires=[
      'numpy',
      'docker==3.1.4',
      'psutil',
      'traitlets>=4.3.2',
      'sqlalchemy',
      'six',
      'scrypt',
      'ipfsapi',
      'jinja2',
      'requests',
      'qiniu',
      'cryptography',
      'Twisted',
      'pycryptodome',
  ],
  classifiers = [
      'Development Status :: 3 - Alpha',
      'Intended Audience :: End Users/Desktop',
      'Topic :: System :: Networking',
      'Programming Language :: Python :: 2.7',
  ],
  entry_points={'console_scripts': ['subgradient=subgradient.main:main'], },
)