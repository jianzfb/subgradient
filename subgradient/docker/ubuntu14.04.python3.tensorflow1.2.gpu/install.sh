#!/usr/bin/env bash
# 1.step install rocksdb
sudo apt-get update
sudo apt-get install -y build-essential libgflags-dev libsnappy-dev zlib1g-dev libbz2-dev liblz4-dev libzstd-dev
git clone https://github.com/facebook/rocksdb.git
cd rocksdb/
make shared_lib
export CPLUS_INCLUDE_PATH=${CPLUS_INCLUDE_PATH}:`pwd`/include
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:`pwd`
export LIBRARY_PATH=${LIBRARY_PATH}:`pwd`
cd ..

# 2.step install ipfs
#wget -q https://raw.githubusercontent.com/ipfs/install-go-ipfs/master/install-ipfs.sh
#chmod +x install-ipfs.sh
#./install-ipfs.sh

# 3.step install graphviz
sudo apt-get install -y graphviz

# 4.step install antgo
git clone https://github.com/jianzfb/antgo.git
cd antgo
sudo apt-get install -y libsnappy-dev zlib1g-dev libbz2-dev liblz4-dev
pip3 install cython>=0.20 -i https://pypi.tuna.tsinghua.edu.cn/simple
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
python3 setup.py build_ext install

# 5.step build factory folder
mkdir /home/factory
ln -s /dataset /home/factory/
