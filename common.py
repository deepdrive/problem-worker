import json
import os
from typing import Tuple

import requests
from botleague_helpers.config import in_test
from botleague_helpers.key_value_store import get_key_value_store

from constants import EVAL_JOBS_COLLECTION_NAME, METADATA_URL


def is_json(string: str):
    try:
        json.loads(string)
    except ValueError:
        return False
    return True


def get_eval_jobs_kv_store():
    return get_key_value_store(
        EVAL_JOBS_COLLECTION_NAME,
        use_boxes=True,
        force_firestore_db=should_force_firestore_db()
    )


def fetch_instance_id() -> Tuple[str, bool]:
    if in_test():
        ret = os.environ['FAKE_INSTANCE_ID']
        is_real = False
    else:
        ret = requests.get(f'{METADATA_URL}/id',
                           headers={'Metadata-Flavor': 'Google'})
        is_real = True
    return ret, is_real


def should_force_firestore_db():
    return os.environ.get('FORCE_FIRESTORE_DB', None) is not None
