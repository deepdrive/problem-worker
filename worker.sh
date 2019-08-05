#!/usr/bin/env bash

pip3 install -r requirements.txt

cp problem_worker_supervisor.conf /etc/supervisor/conf.d/

# Just to be sure
sudo service supervisor start

supervisorctl stop deepdrive-problem-worker
supervisorctl reread
supervisorctl update
supervisorctl start deepdrive-problem-worker

/usr/bin/python3 -u /usr/local/src/problem-worker/worker.py
