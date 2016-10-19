#!/usr/bin/env bash

source env/bin/activate

python buildsvm.py

pm2 restart 1