import inspect
import os
from os.path import join

from botleague_helpers.constants import SHOULD_USE_FIRESTORE

import constants as c
from tests.test_constants import DATA_DIR
from util import get_str_or_json, read_file


class Mockable:
    test_name: str

    def __init__(self):
        self.test_name = get_test_name_from_callstack()
        if not self.test_name:
            raise RuntimeError('Did not find a test method in the call'
                               ' stack!')

    def github_get(self, repo, filename):
        filepath = self.get_test_filename(filename)
        content_str = read_file(filepath)
        ret = get_str_or_json(content_str, filepath)
        return ret

    def get_test_filename(self, filename):
        return join(DATA_DIR, self.test_name, filename)

