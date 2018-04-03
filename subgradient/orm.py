# -*- coding: UTF-8 -*-
# @Time : 30/03/2018
# @File : orm.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function

from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy import (
    inspect,
    Column, Integer, ForeignKey, Unicode, Boolean,
    DateTime,Float,
)
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.expression import bindparam
from sqlalchemy import create_engine, Table
from sqlalchemy import LargeBinary
from sqlalchemy import and_
from sqlalchemy.orm import backref
import json
Base = declarative_base()


class JSONDict(TypeDecorator):
  """Represents an immutable structure as a json-encoded string.

  Usage::

      JSONEncodedDict(255)

  """

  impl = TEXT

  def process_bind_param(self, value, dialect):
    if value is not None:
      value = json.dumps(value)

    return value

  def process_result_value(self, value, dialect):
    if value is not None:
      value = json.loads(value)
    return value


class Container(Base):
  __tablename__ = 'container'

  def __repr__(self):
    return self.container_id

  id = Column(Integer, primary_key=True)
  container_id = Column(Unicode(1024), default='')
  cpu_num = Column(Integer, default=0)
  cpu_mem = Column(Integer, default=0)
  gpu_num = Column(Integer, default=0)
  disk_size = Column(Integer, default=0)

  launch_time = Column(Float, default=0.0)
  apply_duration = Column(Float, default=0.0)
  health = Column(Integer, default=0)       # 1: health;
                                            # 0: no response;
  status = Column(Integer, default=0)       # 1: running;
                                            # 0: stop and exit;
                                            # -1: error and exit;
                                            # -2: stop and no exit;
                                            # -3: error and no exit
  log = Column(LargeBinary, default=None)
  monitor = Column(JSONDict)


def new_session_factory(url="sqlite:///:memory:", reset=False, **kwargs):
  """Create a new session at url"""
  if url.startswith('sqlite'):
    kwargs.setdefault('connect_args', {'check_same_thread': False})
  elif url.startswith('mysql'):
    kwargs.setdefault('pool_recycle', 60)

  if url.endswith(':memory:'):
    # If we're using an in-memory database, ensure that only one connection
    # is ever created.
    kwargs.setdefault('poolclass', StaticPool)

  engine = create_engine(url, **kwargs)
  if reset:
    Base.metadata.drop_all(engine)
  Base.metadata.create_all(engine)

  session_factory = sessionmaker(bind=engine)
  return session_factory