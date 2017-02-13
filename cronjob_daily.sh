#!/usr/bin/env bash

cd "$(dirname "$0")" #change to current directory as working directory
PATH=/usr/local/bin/ices:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH #Updating path for CronJob

. env/bin/activate

python3 buildsvm.py

pm2 restart 0