#!/usr/bin/env bash
cd /antgo
response=`git pull`
if [ "${response}" != "Already up-to-date." ]
then
pip3 uninstall antgo
python3 setup.py build_ext install
fi

