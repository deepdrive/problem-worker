#!/usr/bin/env bash

set -e  # Abort script at first error, when a command exits with non-zero status (except in until or while loops, if-tests, list constructs)
set -u  # Attempt to use undefined variable outputs error message, and forces an exit
set -x  # Similar to verbose mode (-v), but expands commands
set -o pipefail  # Causes a pipeline to return the exit status of the last command in the pipe that returned a non-zero return value.

DIR=`dirname "$0"`
echo ${DIR}
/usr/bin/python3.7 -m pip install -r ${DIR}/requirements.txt
/usr/bin/python3.7 -u ${DIR}/problem-worker/worker.py
