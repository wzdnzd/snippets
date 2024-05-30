#!/bin/bash

##################################
##   @Author  : wzdnzd          ##
##   @Time    : 2023-11-08      ##
##################################

# 定义所需的Python和OpenSSL版本
PYTHON_VERSION=3.11.6
OPENSSL_VERSION=1.1.1w

# 设置Python 3.11.6需要的最低OpenSSL版本
REQUIRED_OPENSSL_VERSION=1.1.1

# openssl 目录
OPENSSL_DIR=/usr/lib/ssl

# 函数来比较版本号
version_gt() { test "$(printf '%s\n' "$@" | sort -V | head -n 1)" != "$1"; }

# 获取当前OpenSSL版本
current_openssl_version=$(openssl version -v | cut -d" " -f2)
echo "当前OpenSSL版本: $current_openssl_version"

# 检查OpenSSL版本是否满足要求
if version_gt $REQUIRED_OPENSSL_VERSION $current_openssl_version; then
  echo "OpenSSL版本不符合要求，需要编译安装新版本"
  # 下载OpenSSL源码
  wget https://www.openssl.org/source/openssl-$OPENSSL_VERSION.tar.gz
  tar -xzf openssl-$OPENSSL_VERSION.tar.gz
  cd openssl-$OPENSSL_VERSION

  # 编译安装OpenSSL
  ./config --prefix=/usr/local/openssl --openssldir=/usr/local/openssl shared zlib
  make
  sudo make install

  # 更新系统库链接
  sudo ldconfig /usr/local/openssl/lib

  # 添加OpenSSL库到环境变量
  echo "/usr/local/openssl/lib" | sudo tee /etc/ld.so.conf.d/openssl-$OPENSSL_VERSION.conf
  sudo ldconfig -v

  # 清理源码目录
  cd ..
  rm -rf openssl-$OPENSSL_VERSION.tar.gz openssl-$OPENSSL_VERSION

  # 更新shell环境变量
  echo "export PATH=/usr/local/openssl/bin:$PATH" >> /etc/profile
  echo "export LD_LIBRARY_PATH=/usr/local/openssl/lib:$LD_LIBRARY_PATH" >> /etc/profile
  source /etc/profile

  OPENSSL_DIR=/usr/local/openssl
  echo "OpenSSL $OPENSSL_VERSION 安装完成"
else
  OPENSSL_DIR=`openssl version -a | grep OPENSSLDIR | cut -d'"' -f2`
  echo "当前OpenSSL版本符合要求"
fi


echo "OpenSSL路径: ${OPENSSL_DIR}"

# 安装Python编译依赖项
sudo apt update
sudo apt install -y build-essential zlib1g-dev libncurses5-dev libgdbm-dev libnss3-dev libssl-dev libreadline-dev libffi-dev libsqlite3-dev wget libbz2-dev

# 下载Python源码
wget https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tar.xz
tar -xf Python-$PYTHON_VERSION.tar.xz
cd Python-$PYTHON_VERSION

# 配置Python构建过程，指定OpenSSL库路径
LD_RUN_PATH=/usr/local/openssl/lib ./configure --enable-optimizations --prefix=/usr/local/python311 --with-openssl=${OPENSSL_DIR}

# 编译安装Python
make -j$(nproc)
sudo make altinstall

# 清理源码目录
cd ..
rm -rf Python-$PYTHON_VERSION.tar.xz Python-$PYTHON_VERSION

# # 更新环境变量
# echo "export PATH=/usr/local/python311/bin:$PATH" >> /etc/profile

# # 添加Python3别名
# echo "alias python3=/usr/local/python311/bin/python3.11" >> /etc/profile
# source /etc/profile

# 修改Python3默认版本
sudo update-alternatives --install /usr/bin/python3 python3 /usr/local/python311/bin/python3.11 1
sudo update-alternatives --config python3

# 验证Python安装
python3 --version

# 安装pip3
sudo apt install python3-pip -y

# wget https://bootstrap.pypa.io/get-pip.py
# python3 get-pip.py
# rm -rf get-pip.py

# 结束脚本
echo "Python $PYTHON_VERSION 安装完成"