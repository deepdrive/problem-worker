#!/usr/bin/env bash

gcloud auth activate-service-account --key-file=/root/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json
gcloud auth configure-docker --quiet
