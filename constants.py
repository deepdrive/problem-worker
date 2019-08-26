import os

SIM_IMAGE_BASE_TAG = 'deepdriveio/private:deepdrive-sim-package'
DOCKERHUB_USERNAME = os.environ.get('DOCKERHUB_USERNAME') or 'crizcraig'
DOCKERHUB_PASSWORD = os.environ.get('DOCKERHUB_PASSWORD')
