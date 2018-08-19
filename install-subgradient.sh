#!/usr/bin/env bash
# 1.step system platform check
os_version=''
os_info=`lsb_release -a`
is_in()
{
    STRING_A=$1
    STRING_B=$2

    if [[ ${STRING_A/${STRING_B}//} == $STRING_A ]]
    then
        return 0
    else
        return 1
    fi
}
is_in "${os_info}" "Centos"
is_centos=$?
if [ ${is_centos} -ne 0 ]; then
	os_version='Centos'
fi
is_in "${os_info}" "Ubuntu"
is_ubuntu=$?
if [ ${is_ubuntu} -ne 0 ]; then
	os_version='Ubuntu'
fi

if [ ${os_version} = '' ]; then
	echo 'subgradient only support Centos and Ubuntu'
	exit 1
fi

## 2.step download and install ipfs
#if [ ! -d "/usr/local/bin/ipfs" ]; then
#wget -q https://raw.githubusercontent.com/ipfs/install-go-ipfs/master/install-ipfs.sh
#chmod +x install-ipfs.sh
#./install-ipfs.sh
#fi

# 3.step download and install docker
# 3.1.step install docker
if [ ${os_version} = 'Ubuntu' ]; then
    sudo apt-get remove docker docker-engine docker.io
    sudo apt-get update
    sudo apt-get install linux-image-extra-$(uname -r) linux-image-extra-virtual

    sudo apt-get update
    sudo apt-get install apt-transport-https ca-certificates curl software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
    sudo apt-get update
    sudo apt-get install docker-ce

fi
if [ ${os_version} = 'Centos' ]; then
    sudo yum install -y yum-utils device-mapper-persistent-data lvm2
    sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo yum install docker-ce
fi

# 3.2.step add current user to docker group
sudo groupadd docker
sudo gpasswd -a ${USER} docker
if [ ${os_version} = 'Ubuntu' ]; then
	sudo service docker restart
fi
if [ ${os_version} = 'Centos']; then
	sudo systemctl restart docker
fi

## 4.step download and install nvidia-docker (if have nvidia gpu)
#if hash nvidia-smi 2>/dev/null; then
#if [ os_version -eq Ubuntu ]; then
## If you have nvidia-docker 1.0 installed: we need to remove it and all existing GPU containers
#docker volume ls -q -f driver=nvidia-docker | xargs -r -I{} -n1 docker ps -q -a -f volume={} | xargs -r docker rm -f
#sudo apt-get purge -y nvidia-docker
#
## Add the package repositories
#curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | \
#  sudo apt-key add -
#distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
#curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
#  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
#sudo apt-get update
#
## Install nvidia-docker2 and reload the Docker daemon configuration
#sudo apt-get install -y nvidia-docker2
#sudo pkill -SIGHUP dockerd
#
## Test nvidia-smi with the latest official CUDA image
#docker run --runtime=nvidia --rm nvidia/cuda nvidia-smi
#fi
#
#fi [ os_version -eq Centos ]; then
## If you have nvidia-docker 1.0 installed: we need to remove it and all existing GPU containers
#docker volume ls -q -f driver=nvidia-docker | xargs -r -I{} -n1 docker ps -q -a -f volume={} | xargs -r docker rm -f
#sudo yum remove nvidia-docker
#
## Add the package repositories
#distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
#curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.repo | \
#  sudo tee /etc/yum.repos.d/nvidia-docker.repo
#
## Install nvidia-docker2 and reload the Docker daemon configuration
#sudo yum install -y nvidia-docker2
#sudo pkill -SIGHUP dockerd
#
## Test nvidia-smi with the latest official CUDA image
#docker run --runtime=nvidia --rm nvidia/cuda nvidia-smi
#fi
#fi

## 7.step install subgradient
#pip install --upgrade subgradient

## 8.step relogin system
#echo 'system must relogin after 10 seconds'
#b=''
#for ((i=0;$i<=10;i+=2))
#do
#printf "time: [%-10s] %ds\r" $b $i
#sleep 1
#b+='>'
#done
#echo
#logout

