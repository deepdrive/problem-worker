import json
import os
from typing import Tuple

import requests
from loguru import logger as log

from botleague_helpers.config import in_test
from botleague_helpers.db import get_db

from problem_constants.constants import JOBS_COLLECTION_NAME, METADATA_URL, \
    WORKER_INSTANCES_COLLECTION_NAME


def is_json(string: str):
    try:
        json.loads(string)
    except ValueError:
        return False
    return True


def get_jobs_db():
    return get_db(
        JOBS_COLLECTION_NAME,
        use_boxes=True,
        force_firestore_db=should_force_firestore_db()
    )


def get_worker_instances_db():
    return get_db(
        WORKER_INSTANCES_COLLECTION_NAME,
        use_boxes=True,
        force_firestore_db=should_force_firestore_db()
    )


def fetch_instance_id() -> Tuple[str, bool]:
    if in_test() or 'INSTANCE_ID' in os.environ:
        ret = os.environ['INSTANCE_ID']
        is_real = False
    else:
        try:
            ret = requests.get(f'{METADATA_URL}/id',
                               headers={'Metadata-Flavor': 'Google'}).text
            log.success('INSTANCE_ID: ' + ret)
        except Exception as e:
            log.error('Unable to get GCP instance metadata. '
                      'Are you on GCP? If not, you can manually'
                      ' set the INSTANCE_ID'
                      ' in your env for testing purposes.')
            exit(1)
        is_real = True
    return ret, is_real


def should_force_firestore_db():
    return os.environ.get('FORCE_FIRESTORE_DB', None) is not None
