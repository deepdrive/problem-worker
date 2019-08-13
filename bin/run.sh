#!/usr/bin/env bash

set -e  # Abort script at first error, when a command exits with non-zero status (except in until or while loops, if-tests, list constructs)
set -u  # Attempt to use undefined variable outputs error message, and forces an exit
set -x  # Similar to verbose mode (-v), but expands commands
set -o pipefail  # Causes a pipeline to return the exit status of the last command in the pipe that returned a non-zero return value.

# For running on cloud VM in docker
DIR=`dirname "$0"`
cd ${DIR}/..

KEY_FILE=/root/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json

chmod -R 665 /root/.gcpcreds

if [[ -f ${KEY_FILE} ]]; then
    echo Adding service account
    gcloud auth activate-service-account --key-file=${KEY_FILE}
    gcloud auth configure-docker --quiet
fi

pip install -r requirements.txt

python -u worker.py
