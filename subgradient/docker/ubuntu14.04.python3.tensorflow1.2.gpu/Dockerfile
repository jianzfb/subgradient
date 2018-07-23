FROM docker.io/nvidia/cuda:8.0-cudnn5-devel-ubuntu14.04

RUN apt-get update -y && apt-get install -y wget \
                       vim \
                       git \
                       curl \
                       wget \
                       python3 \
                       python3-pip \
                       python3-dev \
                       unzip \
                       tar \
                       openssh-server

RUN pip3 install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
RUN pip3 install --upgrade https://storage.googleapis.com/tensorflow/linux/gpu/tensorflow_gpu-1.2.0-cp34-cp34m-linux_x86_64.whl -i https://pypi.tuna.tsinghua.edu.cn/simple --ignore-installed six
RUN apt-get install -y libblas-dev liblapack-dev libatlas-base-dev gfortran
ADD install.sh install.sh
ADD update.sh update.sh
RUN bash install.sh

RUN mkdir /root/.ssh && cd /root/.ssh/ && touch authorized_keys
ADD secret.subgrad.pub /root/.ssh/
RUN cd /root/.ssh && cat secret.subgrad.pub > authorized_keys && chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys && mkdir -p /var/run/sshd
RUN echo "export PATH=$PATH:/usr/local/nvidia/bin:/usr/local/cuda/bin && cd /home/workspace" > /root/.bash_profile


ENV CPLUS_INCLUDE_PATH=${CPLUS_INCLUDE_PATH}:/rocksdb/include
ENV LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/rocksdb
ENV LIBRARY_PATH=${LIBRARY_PATH}:/rocksdb

