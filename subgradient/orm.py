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
    Float,
)
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.expression import bindparam
from sqlalchemy import create_engine
from subgradient.utils import *
import json
import time
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


class ImageRepository(Base):
  __tablename__ = 'imagerepositorys'
  def __repr__(self):
    return '%s:%s'%(self.os_platform, self.os_version)

  id = Column(Integer, primary_key=True)
  server_id = Column(Integer, default=-1)
  os_platform = Column(Unicode(1024), default='')
  os_version = Column(Unicode(1024), default='')
  software_framework = Column(Unicode(1024), default='')
  image_name = Column(Unicode(1024), default='')

  dockerfile = Column(Unicode(4096), default='')
  support_gpu = Column(Boolean, default=False)

  building_start = Column(Float, default=0.0)
  building_stop = Column(Float, default=0.0)
  building_finish = Column(Boolean, default=False)
  is_base = Column(Boolean, default=True)
  hot = Column(Integer, default=0)

  status = Column(Unicode(1024), default='')    # ready, downloading, building, finish, error
  update_time = Column(Float, default=0.0)

  pid = Column(Integer, default=-1)

class Dataset(Base):
  __tablename__ = 'dataset'

  def __repr__(self):
    return self.dataset_name

  id = Column(Integer, primary_key=True)
  dataset_name = Column(Unicode(1024), default='')
  status = Column(Unicode(1024), default='-')    # support, error,
  md5 = Column(Unicode(1024), default='')
  shell = Column(Unicode(1024), default='')
  update_time = Column(Float, default=0.0)


class Stock(Base):
  __tablename__ = 'stocks'
  def __repr__(self):
    return self.name

  id = Column(Integer, primary_key=True)
  name = Column(Unicode(1024), default='')
  cpu_model = Column(Unicode(1024), default='')
  cpu_num = Column(Integer,default=0)
  cpu_mem = Column(Integer, default=0)

  gpu_model = Column(Unicode(1024), default='')
  gpu_num = Column(Integer, default=0)
  gpu_mem = Column(Integer, default=0)
  disk = Column(Integer, default=2)

  disk_write = Column(Integer, default=1)
  disk_read = Column(Integer, default=1)
  net_download = Column(Float, default=0.0)
  net_upload = Column(Float, default=0.0)

  order = relationship("Order", uselist=False, back_populates="stock")
  status = Column(Integer, default=1)               # 1: waiting to on-shelf, 2: waiting off-shelf, 3: on-shelf, 4: off-shelf
  fee = Column(Float, default=0.0)                  #
  charge_unit = Column(Unicode(128), default='h')   #
  max_rental_time = Column(Float, default=0.0)
  min_rental_time = Column(Float, default=0.0)


class Order(Base):
  __tablename__ = 'orders'

  def __repr__(self):
    return self.container_id

  id = Column(Integer, primary_key=True)
  name = Column(Unicode(1024), default='')
  container_id = Column(Unicode(1024), default='')
  image_name = Column(Unicode(1024), default='')
  leaseholder = Column(Unicode(1024), default='')
  renter = Column(Unicode(1024), default='')

  create_time = Column(Float, default=0.0)    # order register time
  launch_time = Column(Float, default=0.0)    # order sign time
  rental_time = Column(Float, default=0.0)    # order rental time
  health = Column(Integer, default=0)         # 1: normal;
                                              # 0: abnormal;
  status = Column(Integer, default=0)         # 1:  running;
                                              # 0:  default
                                              # -1: unkown error;
                                              # 2: waiting schedule
                                              # 3: expire stop
  status_reason = Column(Unicode(1024), default='')

  workspace = Column(Unicode(1024), default='')
  is_notify = Column(Boolean, default=False)

  public_key = Column(Unicode(4096), default='')
  ssh_port = Column(Integer, default=5000)

  punish = Column(Float, default=0.0)
  stock_id = Column(Integer, ForeignKey('stocks.id'))
  stock = relationship("Stock", back_populates="order")
  token = relationship("APIToken", backref="order")
  token_expire_time = Column(Float, default=0.0)
  is_token_refresh = Column(Boolean, default=False)

  running_config = Column(JSONDict)
  platform_config = Column(JSONDict)

  @classmethod
  def find(cls, db, name):
    """Find a user by name.

    Returns None if not found.
    """
    return db.query(cls).filter(cls.name == name).first()

  def new_api_token(self, token=None):
    """Create a new API token

    If `token` is given, load that token.
    """
    return APIToken.new(token=token, order=self)


class APIToken(Base):
  """An API token"""
  __tablename__ = 'api_tokens'

  @declared_attr
  def order_id(cls):
    return Column(Integer, ForeignKey('orders.id', ondelete="CASCADE"), nullable=True)

  id = Column(Integer, primary_key=True)
  hashed = Column(Unicode(1023))
  prefix = Column(Unicode(1023))
  prefix_length = 4
  algorithm = "sha512"
  rounds = 16384
  salt_bytes = 8

  @property
  def token(self):
    raise AttributeError("token is write-only")

  @token.setter
  def token(self, token):
    """Store the hashed value and prefix for a token"""
    self.prefix = token[:self.prefix_length]
    self.hashed = hash_token(token, rounds=self.rounds, salt=self.salt_bytes, algorithm=self.algorithm)

  def __repr__(self):
    if self.order is not None:
      kind = 'order'
      name = self.order.name
    else:
      # this shouldn't happen
      kind = 'owner'
      name = 'unknown'
    return "<{cls}('{pre}...', {kind}='{name}')>".format(
      cls=self.__class__.__name__,
      pre=self.prefix,
      kind=kind,
      name=name,
    )

  @classmethod
  def find(cls, db, token, kind=None):
    """Find a token object by value.

    Returns None if not found.

    `kind='user'` only returns API tokens for users
    `kind='service'` only returns API tokens for services
    """
    prefix = token[:cls.prefix_length]
    # since we can't filter on hashed values, filter on prefix
    # so we aren't comparing with all tokens
    prefix_match = db.query(cls).filter(bindparam('prefix', prefix).startswith(cls.prefix))
    if kind == 'order':
      prefix_match = prefix_match.filter(cls.order_id != None)
    elif kind is not None:
      raise ValueError("kind must be 'order' or None, not %r" % kind)
    for orm_token in prefix_match:
      if orm_token.match(token):
        return orm_token

  def match(self, token):
    """Is this my token?"""
    return compare_token(self.hashed, token)

  @classmethod
  def new(cls, token=None, order=None):
    """Generate a new API token for a user or service"""
    assert order
    db = inspect(order).session

    if token is None:
      token = new_token()
    else:
      if len(token) < 8:
        raise ValueError("Tokens must be at least 8 characters, got %r" % token)
      found = APIToken.find(db, token)
      if found:
        raise ValueError("Collision on token: %s..." % token[:4])
    orm_token = APIToken(token=token)
    if order:
      assert order.id is not None
      orm_token.order_id = order.id
      order.expire_time = time.time() + 24 * 60 * 60

    db.add(orm_token)
    db.commit()
    return token


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