import json
import os
import time

import requests
import docker
from box import Box
from loguru import logger as log

from botleague_helpers.config import blconfig, in_test
from botleague_helpers.key_value_store import get_key_value_store

from constants import JOB_STATUS_RUNNING, JOB_STATUS_FINISHED, \
    BOTLEAGUE_RESULTS_FILEPATH, BOTLEAGUE_RESULTS_DIR, BOTLEAGUE_LOG_BUCKET, \
    BOTLEAGUE_LOG_DIR, EVAL_JOBS_COLLECTION_NAME, JOB_STATUS_TO_START, \
    METADATA_URL
from logs import add_stackdriver_sink

container_run_level = log.level("CONTAINER", no=20, color="<magenta>")

DIR = os.path.dirname(os.path.realpath(__file__))


class EvalWorker:
    def __init__(self):
        self.instance_id = fetch_instance_id()
        self.docker = docker.from_env()
        self.db = get_eval_jobs_kv_store()

    def loop(self, max_iters=None):

        iters = 0
        while True:
            job = self.check_for_jobs()
            if job:
                if job.status == JOB_STATUS_TO_START:
                    self.mark_job_running(job)
                    self.run_job(job)
                    self.mark_job_finished(job)

            # TODO: Send heartbeat every minute? We'll be restarted after
            #  and idle timeout, so not that big of a deal.

            # TODO: Clean up containers and images with LRU and depending on
            #  disk space. Shouldn't matter until more problems and providers
            #  are added.
            iters += 1
            if iters >= max_iters:
                # Used for testing
                return job
            time.sleep(1)

    def check_for_jobs(self) -> Box:
        job_query = self.db.collection.where(
            'instance_id', '==', self.instance_id)
        jobs = list(job_query.stream())
        ret = Box()
        if len(jobs) > 1:
            # We currently only support one job per instance
            raise RuntimeError('Got more than one job for instance')
        elif not jobs:
            print('No job for instance in db')
        else:
            ret = Box(jobs[0].to_dict())
        return ret

    def mark_job_finished(self, job):
        job.status = JOB_STATUS_FINISHED
        self.db.set(job.id, job)

    def mark_job_running(self, job):
        job.status = JOB_STATUS_RUNNING
        self.db.set(job.id, job)

    def run_job(self, job):
        docker_tag = job.eval_spec.docker_tag
        eval_spec = job.eval_spec
        container_env = dict(
            BOTLEAGUE_EVAL_KEY=eval_spec.eval_key,
            BOTLEAGUE_SEED=eval_spec.seed,
            BOTLEAUGE_PROBLEM=eval_spec.problem,
            BOTLEAGUE_RESULT_FILEPATH=BOTLEAGUE_RESULTS_FILEPATH,)
        log.info('Pulling docker image %s...' % docker_tag)
        self.docker.images.pull(docker_tag)
        log.info('Running container %s...' % docker_tag)
        results_mount = f'{DIR}/botleague_results/{eval_spec.eval_id}'
        os.makedirs(results_mount, exist_ok=True)
        container = self.run_container(
            docker_tag,
            env=container_env,
            volumes={
                results_mount: {'bind': BOTLEAGUE_RESULTS_DIR, 'mode': 'rw'}
            })
        run_logs = container.logs().decode()
        log.log('CONTAINER', run_logs)
        log.info('Finished running container %s...' % docker_tag)
        exit_code = container.attrs['State']['ExitCode']
        log_url = self.upload_logs(run_logs,
                                   filename=f'{job.id}.txt')
        results = Box(logs=log_url)
        if exit_code == 0:
            results.update(self.get_results(results_dir=results_mount))
        else:
            results['error'] = \
                f'Container failed with exit code {exit_code}'
        job.results = results

        self.send_results(job)

    @staticmethod
    def send_results(job):
        if in_test():
            return
        else:
            requests.post(job.results_callback, json=job.to_dict())

    @staticmethod
    def get_results(results_dir) -> dict:
        results = {}
        result_str = open(f'{results_dir}/results.json').read()
        if is_json(result_str):
            results.update(json.loads(result_str))
        else:
            results['error'] = \
                f'No results file found at {BOTLEAGUE_RESULTS_FILEPATH}'
        return results

    def run_container(self, docker_tag, cmd=None, env=None, volumes=None):
        container = self.docker.containers.run(docker_tag, command=cmd,
                                               detach=True, stdout=False,
                                               stderr=False,
                                               environment=env,
                                               volumes=volumes)
        while container.status in ['created', 'running']:
            container = self.docker.containers.get(container.short_id)
            time.sleep(0.1)
        return container

    @staticmethod
    def upload_logs(logs, filename):
        # Upload the logs, auth is by virtue of VM access level

        from google.cloud import storage
        key = f'{BOTLEAGUE_LOG_DIR}/{filename}'
        bucket = storage.Client().get_bucket(BOTLEAGUE_LOG_BUCKET)
        blob = bucket.get_blob(key)
        blob = blob if blob is not None else bucket.blob(key)
        blob.upload_from_string(logs)
        url = f'https://storage.googleapis.com/{BOTLEAGUE_LOG_BUCKET}/{key}'
        return url


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


def play():
    add_stackdriver_sink(log, instance_id='asdf')
    log.error('asdfasdf')
    # worker = EvalWorker()
    # local_results_dir = f'{DIR}/botleague_results'
    # os.makedirs(local_results_dir, exist_ok=True)
    # container = worker.run_container(
    #     'python:3.7',
    #     cmd='bash -c "echo {} > /mnt/botleague/results.json"',
    #     volumes={local_results_dir: {'bind': '/mnt/botleague', 'mode': 'rw'}},)
    # results = open(f'{local_results_dir}/results.json').read()
    # print(results)
    # image = worker.docker.images.get(
    #     '14a2caeca3271219d4aca13d0e9daafd4553fe2f990179a66d8932e5afce805f')
    # image.tag('qwer')
    # asdf = worker.get_file_from_stopped_container(
    #     container, filename='/mnt/botleague/results.json')
    # print(asdf)
    # print(container.logs().decode())
    # log.info(container2.run('cat ~/.bashrc').decode())
    # log.info(container2.logs())

    pass


def should_force_firestore_db():
    return os.environ.get('FORCE_FIRESTORE_DB', None) is not None


def fetch_instance_id():
    if in_test():
        ret = os.environ['FAKE_INSTANCE_ID']
    else:
        ret = requests.get(f'{METADATA_URL}/id',
                           headers={'Metadata-Flavor': 'Google'})
    return ret


if __name__ == '__main__':
    play()
    # main()

