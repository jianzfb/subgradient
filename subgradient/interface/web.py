# -*- coding: UTF-8 -*-
# @Time : 2018/5/21
# @File : web.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
from twisted.internet import protocol
from twisted.web.resource import Resource,NoResource
from twisted.web.server import Site
from twisted.web.static import File
from jinja2 import Environment, FileSystemLoader
from subgradient.context import *
from subgradient import orm
from sqlalchemy import and_,or_
from subgradient.subgrad.chain.api import *
from subgradient.concurrency import *
import os
import json
import time
import cgi
import uuid
import requests
from twisted.internet import task
from twisted.internet.threads import deferToThread
from six.moves import urllib
import multiprocessing
import signal
import shutil
import logging

PATH = os.path.dirname(os.path.abspath(__file__))
PATH = '/'.join(PATH.split('/')[:-1])
TEMPLATE_ENVIRONMENT = Environment(
  autoescape=False,
  loader=FileSystemLoader(os.path.join(PATH, 'resource','templates')),
  trim_blocks=False)

def render_template(template_filename, context):
  return TEMPLATE_ENVIRONMENT.get_template(template_filename).render(context)


class UpdateStockAPIHandler(Resource):
  def render_POST(self, request):
    ctx = get_global_context()

    if 'stock_id' not in request.args:
      # add stock
      cpu_num = int(request.args['cpu_num'][0])
      cpu_mem = int(request.args['memory'][0])

      disk_size = int(request.args['disk_size'][0])
      fee = request.args['fee'][0]
      charge_unit = request.args['charge_unit'][0]
      charge_unit = 'h'
      min_rental_time = float(request.args['min_rental_time'][0])
      max_rental_time = float(request.args['max_rental_time'][0])

      if fee == '':
        request.setResponseCode(500)
        return ''.encode('utf-8')

      cpu_model = ctx.schedule.cpu.cpu_model_name(0)
      gpu_model = ''
      gpu_num = 0
      gpu_mem = 0
      if ctx.schedule.gpu.is_gpu_ok:
        gpu_num = int(request.args['gpu_num'][0])
        gpu_mem = int(float(request.args['gpu_memory'][0]))
        gpu_model = ctx.schedule.gpu.gpu_model_name(0)

      ss = orm.Stock(name='',
                cpu_model=cpu_model,
                cpu_num=cpu_num,
                cpu_mem=cpu_mem,
                gpu_model=gpu_model,
                gpu_num=gpu_num,
                gpu_mem=gpu_mem,
                disk=disk_size,
                fee=float(fee),
                charge_unit=charge_unit,
                max_rental_time=max_rental_time,
                min_rental_time=min_rental_time,
                status=1)

      ctx.db.add(ss)
      ctx.db.commit()
      return ''.encode('utf-8')

    stock_id = request.args['stock_id'][0]
    stock_status = request.args['status'][0]
    stock_id = int(stock_id)

    if stock_status == 'true':
      stock_status = True
    else:
      stock_status = False

    stock = ctx.db.query(orm.Stock).filter(orm.Stock.id == stock_id).one_or_none()
    if stock is None:
      request.setResponseCode(500)
      return ''.encode('utf-8')

    if stock_status:
      # waiting to onshelf
      stock.status = 1
    else:
      # waiting to offshelf
      stock.status = 2

    ctx.db.commit()
    return ''.encode('utf-8')


class UpdateImageAPIHandler(Resource):
  def render_POST(self, request):
    # 1.step parse parameter
    image_name = request.args['image_name'][0]
    image_name = image_name.lower()
    os_platform = request.args['os_platform'][0]
    os_version = request.args['os_version'][0]
    software_platform = request.args['software_platform'][0]
    support_gpu = request.args['support_gpu'][0]
    support_gpu = True if support_gpu == 'true' else False
    dockerfile = request.args['dockerfile'][0]

    # 2.step check info complete
    ctx = get_global_context()
    result = ctx.image_manage.image_status(image_name)
    if result['result'] != 'not existed':
      request.setResponseCode(500)
      return json.dumps({'reason': 'IMAGE_NAME_NOT_UNIQUE'}).encode('utf-8')

    if not os.path.exists(os.path.join(ctx.image_manage.dockerfile_factory,dockerfile)):
      request.setResponseCode(500)
      return json.dumps({'reason': 'NO_DOCKERFILE_ERROR'}).encode('utf-8')

    # 3.step (defer) building image
    result = ctx.image_manage.build_image(dockerfile,
                                          image_name,
                                          os_platform=os_platform,
                                          os_version=os_version,
                                          software_platform=software_platform,
                                          support_gpu=support_gpu,is_base=True)
    if not result:
      request.setResponseCode(500)
      return json.dumps({'reason': 'BUILD_IMAGE_ERROR'}).encode('utf-8')

    return json.dumps({}).encode('utf-8')


class CancelOrderAPIHandler(Resource):
  def render_POST(self, request):
    #
    order_id = request.args['order_id'][0]
    ctx = get_global_context()
    order = ctx.db.query(orm.Order).filter(orm.Order.name == order_id).one_or_none()
    if order is None:
      request.setResponseCode(500)
      return json.dumps({})

    result = ctx.subgradient_chain_api.put(order_id=order_id,
                     action='update',
                     status='cancel::')

    if result is None:
      request.setResponseCode(500)
      return json.dumps({'result': 'fail'})
    else:
      order.status = -1
      order.is_notify = True
      ctx.db.commit()
      return json.dumps({'result': 'success'})


class DockerfileListAPIHandler(Resource):
  def render_GET(self, request):
    ctx = get_global_context()
    cp = request.args['cp'][0]
    ps = request.args['ps'][0]

    objs = ctx.subgradient_server_api.get_dockerfile_list(cp=cp, ps=ps)
    if objs is None:
      return json.dumps([])

    # 1.step parse result content and add record
    # objs = json.loads(result.content)
    # 'OS_PLATFORM': 'ubuntu',
    # 'OS_VERSION': '12.0',
    # 'SOFTWARE_FRAMEWORK': 'conda',
    # 'GPU': 'support',
    # "IMAGE": 'www',
    # 'HOT': 1,
    # 'ID': 0,
    # 'UPDATE': ..
    local_images = ctx.db.query(orm.ImageRepository).all()
    local_images_ids = [image.server_id for image in local_images]
    local_images_ids_map = {image.server_id: image for image in local_images}

    cloud_images_ids = [int(obj['ID']) for obj in objs['rows']]
    cloud_images_ids_map = {int(obj['ID']): obj for obj in objs['rows']}
    # # 2.step need to delete
    # for local_image_index, local_image_id in enumerate(local_images_ids):
    #   if local_image_id not in cloud_images_ids:
    #     ctx.db.delete(local_images[local_image_index])

    # 3.step need to update
    for cloud_image_id in cloud_images_ids:
      local_image = None
      if cloud_image_id in local_images_ids:
        image_info = cloud_images_ids_map[cloud_image_id]
        local_image = local_images_ids_map[cloud_image_id]
        if image_info['UPDATE'] > local_image.update_time:
          local_image.os_platform = image_info['OS_PLATFORM']
          local_image.os_version = image_info['OS_VERSION']
          local_image.software_framework = image_info['SOFTWARE_FRAMEWORK']
          local_image.support_gpu = True if image_info['GPU'] == 'support' else False
          local_image.dockerfile = image_info['DOCKERFILE']
          local_image.image_name = image_info['IMAGE']
          local_image.update_time = image_info['UPDATE']
          local_image.hot = image_info['HOT']
          local_image.status = ''   # 重置镜像状态
      else:
        image_info = cloud_images_ids_map[cloud_image_id]
        local_image = orm.ImageRepository(server_id=image_info['ID'],
                                    os_platform=image_info['OS_PLATFORM'],
                                    os_version=image_info['OS_VERSION'],
                                    software_framework=image_info['SOFTWARE_FRAMEWORK'],
                                    support_gpu=True if image_info['GPU'] == 'support' else False,
                                    dockerfile=image_info['DOCKERFILE'],
                                    image_name=image_info['IMAGE'],
                                    status='',
                                    hot=image_info['HOT'],
                                    update_time=image_info['UPDATE'])
        ctx.db.add(local_image)

      # 2.step fill image local status
      image_info['STATUS'] = local_image.status
      if local_image.status in ['downloading', 'building', 'ready', 'finish']:
        if local_image.status in ['downloading', 'building']:
          # check buildint start time
          if (time.time() - local_image.building_start) / (60 * 60) > 4:
            local_image.status = 'error'
            if local_image.pid > 0:
              # kill old build image process
              os.kill(local_image.pid, signal.SIGKILL)

            image_info['OPERATOR'] = 'build'
        else:
          image_info['OPERATOR'] = '-'
      else:
        image_info['OPERATOR'] = 'build'

    ctx.db.commit()
    return json.dumps(objs)


def _download_dockerfile(info):
  dockerfile_db = info['dockerfile_db']
  ctx = info['ctx']
  dockerfile_factory = ctx.image_manage.dockerfile_factory
  # dockerfile_url = 'http://%s:%d/api/download/dockerfile?id=%d'%(ctx.server_ip,
  #                                                            ctx.server_port,
  #                                                            int(dockerfile_db.server_id))
  dockerfile_db.status = 'downloading'
  ctx.db.commit()

  if not os.path.exists(dockerfile_factory):
    os.makedirs(dockerfile_factory)

  random_folder, _ = os.path.normpath(dockerfile_db.dockerfile).split('/')
  if not os.path.exists(os.path.join(dockerfile_factory, random_folder)):
    os.makedirs(os.path.join(dockerfile_factory, random_folder))

  fpath = os.path.join(dockerfile_factory, dockerfile_db.dockerfile)

  try:
    statinfo = ctx.subgradient_server_api.download(filecategory='dockerfile',
                                                   filename=dockerfile_db.server_id,
                                                   filepath=fpath)

    size = statinfo.st_size
  except:
    logging.error('failed to download dockerfile {}'.format(dockerfile_db.server_id))
    dockerfile_db.status = 'error'
    ctx.db.commit()
    raise
  assert size > 0, "download an empty file!"

  logging.info('succesfully downloaded ' + dockerfile_db.dockerfile + " " + str(size) + ' bytes.')
  return info

def _build_dockerfile_image(info):
  ctx = info['ctx']
  dockerfile_db = info['dockerfile_db']
  dockerfile_db.status = 'building'
  ctx.db.commit()

  # copy publick key to
  result = ctx.image_manage.build_image(dockerfile_db.dockerfile,
                                    dockerfile_db.image_name,
                                    os_platform=dockerfile_db.os_platform,
                                    os_version=dockerfile_db.os_version,
                                    software_platform=dockerfile_db.software_framework,
                                    support_gpu=dockerfile_db.support_gpu)
  if result:
    image_result = ctx.image_manage.image_status(dockerfile_db.image_name)
    if image_result['result'] == 'existed':
      # success
      dockerfile_db.building_stop = time.time()
      dockerfile_db.building_finish = True
      dockerfile_db.status = 'finish'
      ctx.db.commit()
    else:
      dockerfile_db.status = 'error'
      ctx.db.commit()
  else:
    dockerfile_db.status = 'error'
    ctx.db.commit()


class BuildImageProcess(multiprocessing.Process):
  def __init__(self, info):
    super(BuildImageProcess, self).__init__()
    self.info = info

  def run(self):
    try:
      logging.info('start build image process (pid=%s)'%str(os.getpid()))
      # update dockerfile pid
      self.info['dockerfile_db'].pid = os.getpid()
      self.info['ctx'].db.commit()

      # 1.step download dockerfile from server
      _download_dockerfile(self.info)

      # 2.step build image from dockerfile
      _build_dockerfile_image(self.info)

      logging.info('stop build image process (pid=%s)'%str(os.getpid()))
    except:
      pass


class BuildImageAPIHandler(Resource):
  def render_POST(self, request):
    ctx = get_global_context()

    # 0.step get image basic informatino
    image_id = request.args['ID'][0]
    image = ctx.db.query(orm.ImageRepository).filter(orm.ImageRepository.server_id == int(image_id)).one_or_none()
    if image is None:
      request.setResponseCode(500)
      return

    if image.status in ['ready','downloading', 'building', 'finish']:
      return json.dumps({'result': 'fail', 'reason': image.status})

    image.status = 'ready'
    image.building_start = time.time()
    ctx.db.commit()

    build_process = BuildImageProcess({'ctx': ctx,'dockerfile_db': image})
    build_process.start()

    return json.dumps({})


def _download_dataset_shell(ctx, dataset):
  shell_factory = os.path.join(ctx.workspace, 'shell')
  if not os.path.exists(shell_factory):
    os.makedirs(shell_factory)

  fpath = os.path.join(shell_factory, dataset.shell)

  try:
    statinfo = ctx.subgradient_server_api.download(filecategory='datasetshell',
                                                   filename=dataset.dataset_name,
                                                   filepath=fpath)
    size = statinfo.st_size
  except:
    logging.error('failed to download {}'.format(dataset.shell))
    raise
  assert size > 0, "download an empty file!"

  logging.info('succesfully downloaded ' + dataset.shell + " " + str(size) + ' bytes.')


class DatasetListAPIHandler(Resource):
  def render_GET(self, request):
    ctx = get_global_context()
    cp = request.args['cp'][0]
    ps = request.args['ps'][0]

    objs = ctx.subgradient_server_api.get_dataset_list(cp=cp, ps=ps)
    if objs is None:
      return json.dumps({})

    local_datasets = ctx.db.query(orm.Dataset).all()
    local_datasets_names = [dataset.dataset_name for dataset in local_datasets]
    local_datasets_names_map = {dataset.dataset_name: dataset for dataset in local_datasets}

    cloud_datasets_names = [obj['DATASET'] for obj in objs['rows']]
    cloud_datasets_names_map = {obj['DATASET']: obj for obj in objs['rows']}

    # 3.step need to update
    for cloud_dataset_name in cloud_datasets_names:
      local_dataset = None
      if cloud_dataset_name in local_datasets_names:
        dataset_info = cloud_datasets_names_map[cloud_dataset_name]
        local_dataset = local_datasets_names_map[cloud_dataset_name]
        if dataset_info['UPDATE'] > local_dataset.update_time:
          local_dataset.shell = dataset_info['SHELL']
          local_dataset.update_time = float(dataset_info['UPDATE'])
          local_dataset.status = '-'    # 重置状态
      else:
        dataset_info = cloud_datasets_names_map[cloud_dataset_name]
        local_dataset = orm.Dataset(dataset_name=dataset_info['DATASET'],
                              shell=dataset_info['SHELL'],
                              update_time=dataset_info['UPDATE'])
        ctx.db.add(local_dataset)

      dataset_info['STATUS'] = local_dataset.status
      dataset_info['OPERATOR'] = local_dataset.status

    ctx.db.commit()
    return json.dumps(objs)


class CheckDatasetProcess(multiprocessing.Process):
  def __init__(self, info):
    super(CheckDatasetProcess, self).__init__()
    self.info = info

  def run(self):
    try:
      logging.info('start check dataset process (pid=%s)'%str(os.getpid()))

      ctx = self.info['ctx']
      dataset = self.info['dataset']
      # 1.step check .sh file
      if not os.path.exists(os.path.join(self.info['ctx'].workspace, 'shell', self.info['dataset'].shell)):
        # download shell file from server
        _download_dataset_shell(self.info['ctx'], self.info['dataset'])
        if not os.path.exists(os.path.join(self.info['ctx'].workspace, 'shell', self.info['dataset'].shell)):
          logging.error('fail to download dataset check shell')
          return

      # 2.step run .sh, waiting result
      result = os.popen('bash %s' % os.path.join(ctx.workspace, 'shell', dataset.shell)).read()
      result = result.strip()
      result = json.loads(result)
      if result['result'] == 'success':
        dataset.status = 'support'
        ctx.db.commit()

      logging.info('stop check dataset process (pid=%s)'%str(os.getpid()))
    except:
      dataset.status = 'error'
      ctx.db.commit()
      logging.error('fail to check dataset')


class DatasetCheckAPIHandler(Resource):
  def render_POST(self, request):
    ctx = get_global_context()

    dataset_name = request.args['DATASET'][0]
    dataset = ctx.db.query(orm.Dataset).filter(orm.Dataset.dataset_name == dataset_name).one_or_none()
    if dataset is None:
      request.setResponseCode(500)
      return json.dumps({})

    if dataset.status == 'support':
      return json.dumps({})

    info = {'ctx': ctx, 'dataset': dataset}
    cdp = CheckDatasetProcess(info)
    cdp.run()
    return json.dumps({})


class APIHandler(Resource):
  def getChild(self, path, request):
    path_str = path.decode()
    keys = os.path.normpath(path_str).split('/')
    if keys[0] == 'update_stock':
      return UpdateStockAPIHandler()
    elif keys[0] == 'image':
      return UpdateImageAPIHandler()
    elif keys[0] == 'cancel_order':
      return CancelOrderAPIHandler()
    elif keys[0] == 'dockerfile_list':
      return DockerfileListAPIHandler()
    elif keys[0] == 'buildimage':
      return BuildImageAPIHandler()
    elif keys[0] == 'dataset_list':
      return DatasetListAPIHandler()
    elif keys[0] == 'dataset_check':
      return DatasetCheckAPIHandler()

    return NoResource()


class UploadDockerfile(Resource):
  def render_POST(self, request):
      self.headers = request.getAllHeaders()
      uploaded_file_storage = cgi.FieldStorage(fp = request.content,
                                               headers = self.headers,
                                               environ = {'REQUEST_METHOD':'POST',
                                                          'CONTENT_TYPE': self.headers['content-type'],})

      file_name = uploaded_file_storage.list[0].filename
      if '.tar.gz' not in file_name and '.zip' not in file_name:
        request.setResponseCode(500)
        return json.dumps({}).encode('utf-8')

      ctx = get_global_context()
      random_folder = str(uuid.uuid4())
      os.makedirs(os.path.join(ctx.image_manage.dockerfile_factory, random_folder))
      out = open('%s/%s/%s'%(ctx.image_manage.dockerfile_factory, random_folder, file_name), 'wb')
      out.write(uploaded_file_storage.getvalue('filename'))
      out.close()

      return json.dumps({'filename': '%s/%s'%(random_folder, file_name)}).encode('utf-8')


class AdminPage(Resource):
  def getChild(self, path, request):
    if path == '':
      return self

    path_str = path.decode()
    keys = os.path.normpath(path_str).split('/')
    if keys[0] == 'api':
      return APIHandler()
    elif keys[0] == 'upload':
      return UploadDockerfile()

    return NoResource()

  def render_GET(self, request):
    # render admin page
    ctx = get_global_context()
    hardware_list = {'cpu': [], 'cpu_num': 0, 'cpu_select': []}
    # hardware resource list
    cpu_models = ctx.schedule.cpu.cpu_model_name()
    cpu_quota = ctx.schedule.schedule_cpu_quota
    mem_quota = ctx.schedule.schedule_cpu_mem_quota

    for cpu_i, cpu_model in enumerate(cpu_models):
      if cpu_i >= cpu_quota:
        break
      hardware_list['cpu'].append(cpu_model)
      hardware_list['cpu_select'].append(cpu_i + 1)

    hardware_list['cpu_num'] = len(hardware_list['cpu'])
    hardware_list['mem'] = mem_quota
    hardware_list['mem_select'] = [str(mem_q+1) for mem_q in range(int(mem_quota))]

    if ctx.schedule.gpu.is_gpu_ok:
      gpu_models = ctx.schedule.gpu.gpu_model_name()
      gpu_mem = ctx.schedule.schedule_gpu_mem_quota
      gpu_quota = ctx.schedule.schedule_gpu_quota

      hardware_list['gpu'] = []
      hardware_list['gpu_mem'] = []
      hardware_list['gpu_mem_select'] = []
      hardware_list['gpu_num'] = 0
      hardware_list['gpu_select'] = []
      for gpu_i, gpu_model in enumerate([gpu_models[i] for i in gpu_quota]):
        hardware_list['gpu'].append(gpu_model)
        hardware_list['gpu_select'].append(gpu_i + 1)

      hardware_list['gpu_num'] = len(gpu_quota)
      hardware_list['gpu_mem_select'] = [gpu_mem]
      hardware_list['gpu_mem'] = gpu_mem
    else:
      hardware_list['gpu'] = ['']
      hardware_list['gpu_mem'] = 0
      hardware_list['gpu_num'] = 0
      hardware_list['gpu_mem_select'] = [0]
      hardware_list['gpu_select'] = [0]

    hardware_list['disk_select'] = [2,4,8,16,32]

    # Stock
    current_stocks = []
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

      current_stocks.append({'index': stock_i,
                             'id': stock.id,
                             'cpu_num': stock.cpu_num,
                             'cpu_mem': stock.cpu_mem,
                             'gpu_num': stock.gpu_num,
                             'gpu_mem': stock.gpu_mem,
                             'disk': stock.disk,
                             'fee': stock.fee,
                             'charge_unit': stock.charge_unit,
                             'max_rental_time': max_rental_time,
                             'min_rental_time': min_rental_time,
                             'status': stock_status})

    # all orders
    current_processing_orders = []
    orders = ctx.db.query(orm.Order).filter(or_(orm.Order.status == 1,
                                                orm.Order.status == 2,
                                                orm.Order.status == 0)).all()

    for order_index, order in enumerate(orders):
      running_status = ''
      if order.status == 0:
        running_status = 'waiting'
      elif order.status == 1:
        running_status = 'running'
      else:
        running_status = 'schedule'

      order_name = order.name
      renter = order.renter if order.renter != '' else '-'                    # 租户
      rental_time = order.rental_time if order.rental_time > 0.0 else '-'     # 租户租赁时间
      create_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(order.create_time)) if order.create_time > 0.0 else '-'   # 订单上线时间
      launch_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(order.launch_time)) if order.launch_time > 0.0 else '-'   # 租户签约时间
      rental_expire_time = time.strftime('%Y-%m-%d %H:%M:%S',
                                         time.localtime(order.launch_time + order.rental_time * 60 * 60)) \
        if order.launch_time > 0.0 and order.rental_time > 0.0 else '-'      # 租户到期时间
      container_id = order.container_id if order.container_id !='' else '-'  # 租户容器ID
      image_name = order.image_name if order.image_name !='' else '-'       # 租户镜像名称

      current_processing_orders.append({'index': order_index,
                                        'renter': renter,
                                        'name': order_name,
                                        'create_time': create_time,
                                        'launch_time': launch_time,
                                        'rental_time': rental_time,
                                        'rental_expire_time': rental_expire_time,
                                        'container_id': container_id,
                                        'cpu_num': order.stock.cpu_num,
                                        'cpu_mem': order.stock.cpu_mem,
                                        'gpu_num': order.stock.gpu_num,
                                        'gpu_mem': order.stock.gpu_mem,
                                        'punish': order.punish,
                                        'image': image_name,
                                        'status': running_status,
                                        'fee': order.stock.fee,
                                        'charge_unit': order.stock.charge_unit,
                                        'stock_id': order.stock.id})


    # building base images
    base_images = ctx.db.query(orm.ImageRepository).filter(orm.ImageRepository.is_base == True).all()
    base_image_info = []
    for base_image_index, base_image in enumerate(base_images):
      base_image_info.append({'index': base_image_index,
                              'os_platform': base_image.os_platform,
                              'os_version': base_image.os_version,
                              'software_framework': base_image.software_framework,
                              'image_name': base_image.image_name,
                              'dockerfile': base_image.dockerfile,
                              'support_gpu': 'yes' if base_image.support_gpu else 'no',
                              'building_start': time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(base_image.building_start)),
                              'building_stop': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(base_image.building_start)) if base_image.building_finish else '-',
                              'status': 'finish' if base_image.building_finish else 'processing'})

    # money and frozen_money
    my_money = ctx.subgradient_chain_api.money

    ss = render_template('admin.html', {'hardware': hardware_list,
                                        'stocks': current_stocks,
                                        'orders': current_processing_orders,
                                        'base_images': base_image_info,
                                        'money': my_money['money'],
                                        'frozen_money': my_money['frozen_money']})
    return ss.encode('utf-8')


def web_handlers():
  admin_page = AdminPage()
  parent_folder = '/'.join(os.path.dirname(__file__).split('/')[0:-1])
  admin_page.putChild('static', File(os.path.join(parent_folder, 'resource','static')))
  ctx = get_global_context()
  admin_page.putChild('dockerfile',File(ctx.image_manage.dockerfile_factory))

  return admin_page
