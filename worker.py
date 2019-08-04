import json
import os
import time
import logging as log

import requests
import docker
from botleague_helpers.config import blconfig, in_test
from botleague_helpers.key_value_store import get_key_value_store
from box import Box

from constants import JOB_STATUS_RUNNING, JOB_STATUS_FINISHED, \
    BOTLEAGUE_RESULTS_FILEPATH, BOTLEAGUE_RESULTS_DIR, BOTLEAGUE_LOG_BUCKET, \
    BOTLEAGUE_LOG_DIR, EVAL_JOBS_COLLECTION_NAME, JOB_STATUS_TO_START, \
    METADATA_URL

log.basicConfig(level=log.INFO)

DIR = os.path.dirname(os.path.realpath(__file__))


class EvalWorker:
    def __init__(self):
        self.docker = docker.from_env()

    def loop(self, max_iters=None):
        instance_id = self.get_instance_id()
        jobs_kv = get_eval_jobs_kv_store()
        iters = 0
        while True:
            job_query = jobs_kv.collection.where(
                'instance_id', '==', instance_id)
            jobs = list(job_query.stream())
            if len(jobs) > 1:
                raise RuntimeError('Got more than one job for instance')
            elif not jobs:
                print('No job for instance in db')
            else:
                job = Box(jobs[0].to_dict())
                if job.status == JOB_STATUS_TO_START:
                    self.mark_job_running(job, jobs_kv)
                    self.run_job(job)
                    self.mark_job_finished(job, jobs_kv)

            # TODO: Send heartbeat every minute? We'll be restarted after
            #  and idle timeout, so not that big of a deal.

            # TODO: Clean up containers and images with LRU and depending on
            #  disk space. Shouldn't matter until more problems and providers
            #  are added.
            iters += 1
            if iters >= max_iters:
                break
            time.sleep(1)

    @staticmethod
    def get_instance_id():
        if in_test():
            ret = os.environ.get('FAKE_INSTANCE_ID', '3592331990274327389')
        else:
            ret = requests.get(f'{METADATA_URL}/id',
                               headers={'Metadata-Flavor': 'Google'})
        return ret

    @staticmethod
    def mark_job_finished(job, jobs_kv):
        job.status = JOB_STATUS_FINISHED
        jobs_kv.set(job.id, job)

    @staticmethod
    def mark_job_running(job, jobs_kv):
        job.status = JOB_STATUS_RUNNING
        jobs_kv.set(job.id, job)

    def run_job(self, job):
        docker_tag = job.eval_spec.docker_tag
        eval_spec = job.eval_spec
        container_env = dict(
            BOTLEAGUE_EVAL_KEY=eval_spec.eval_key,
            BOTLEAGUE_SEED=eval_spec.seed,
            BOTLEAUGE_PROBLEM=eval_spec.problem,
            BOTLEAGUE_RESULT_FILEPATH=BOTLEAGUE_RESULTS_FILEPATH,)
        log.info('pulling docker image %s...', docker_tag)
        log.info(self.docker.images.pull(docker_tag))
        log.info('Running container %s...', docker_tag)
        results_mount = f'{DIR}/botleague_results/{eval_spec.eval_id}'
        os.makedirs(results_mount, exist_ok=True)
        container = self.run_container(
            docker_tag,
            env=container_env,
            volumes={
                results_mount: {'bind': BOTLEAGUE_RESULTS_DIR, 'mode': 'rw'}
            })
        job_name = self.get_job_name(eval_spec)
        exit_code = container.attrs['State']['ExitCode']
        log_url = self.upload_logs(container.logs(),
                                   filename=f'{job_name}.txt')
        results = dict(logs=log_url)
        if exit_code == 0:
            results.update(self.get_results(results_dir=results_mount))
        else:
            results['error'] = \
                f'Container failed with exit code {exit_code}'
        job.results = results
        requests.post(job.results_callback, json=job)

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
    def get_job_name(eval_spec):
        log_name = f'{eval_spec.problem}_{eval_spec.eval_id}'
        return log_name

    @staticmethod
    def upload_logs(logs, filename):
        # Upload the logs, auth is by virtue of VM access level

        from google.cloud import storage
        key = f'{BOTLEAGUE_LOG_DIR}/{filename}'
        bucket = storage.Client().get_bucket(BOTLEAGUE_LOG_BUCKET)
        blob = bucket.get_blob(key)
        blob = blob if blob is not None else bucket.blob(key)
        blob.upload_from_string(logs)
        url = f'https://storage.googleapis.com/{bucket}/{key}'
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
        force_firestore_db=True  # TODO: REMOVE THIS
    )


def play():
    worker = EvalWorker()
    local_results_dir = f'{DIR}/botleague_results'
    os.makedirs(local_results_dir, exist_ok=True)
    container = worker.run_container(
        'python:3.7',
        cmd='bash -c "echo {} > /mnt/botleague/results.json"',
        volumes={local_results_dir: {'bind': '/mnt/botleague', 'mode': 'rw'}},)
    results = open(f'{local_results_dir}/results.json').read()
    print(results)
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


if __name__ == '__main__':
    play()
    # main()

