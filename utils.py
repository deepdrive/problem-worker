import json
import os
import os.path as p
from datetime import datetime

from box import Box

import logging as log

log.basicConfig(level=log.INFO)


def get_str_or_box(content_str, filename):
    if filename.endswith('.json') and content_str:
        ret = Box(json.loads(content_str))
    else:
        ret = content_str
    return ret


def write_json(obj, path):
    with open(path, 'w') as f:
        json.dump(obj, f, indent=2)


def read_json(filename):
    with open(filename) as file:
        results = json.load(file)
    return results


def write_file(content, path):
    with open(path, 'w') as f:
        f.write(content)


def read_file(path):
    with open(path) as f:
        ret = f.read()
    return ret


def read_lines(path):
    content = read_file(path)
    lines = content.split()
    return lines


def append_file(path, strings):
    with open(path, 'a') as f:
        f.write('\n'.join(strings) + '\n')


def exists_and_unempty(problem_filename):
    return p.exists(problem_filename) and os.stat(problem_filename).st_size != 0


def is_docker():
    path = '/proc/self/cgroup'
    return (
        os.path.exists('/.dockerenv') or
        os.path.isfile(path) and any('docker' in line for line in open(path))
    )


def generate_rand_alphanumeric(num_chars):
    from secrets import choice
    import string
    alphabet = string.ascii_lowercase + string.digits
    ret = ''.join(choice(alphabet) for _ in range(num_chars))
    return ret


def get_sortable_time_string():
    ret = datetime.utcnow().strftime('%Y-%m-%d_%I-%M-%S%p')
    return ret


def dbox(obj):
    return Box(obj, default_box=True)
