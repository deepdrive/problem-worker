import json
import os
from typing import Optional

import re

from botleague_helpers.crypto import decrypt_symmetric, encrypt_db_key
from botleague_helpers.db import get_db
from datetime import datetime

import time
from copy import deepcopy
from random import random

import requests
import docker
from box import Box, BoxList
from docker.models.images import Image
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from loguru import logger as log

from botleague_helpers.config import in_test

from auto_updater import pull_latest, AutoUpdater
from common import is_json, get_jobs_db, fetch_instance_id, \
    get_worker_instances_db, get_secrets_db
from problem_constants.constants import JOB_STATUS_RUNNING, \
    JOB_STATUS_FINISHED, \
    BOTLEAGUE_RESULTS_FILEPATH, BOTLEAGUE_RESULTS_DIR, BOTLEAGUE_LOG_BUCKET, \
    BOTLEAGUE_LOG_DIR, CONTAINER_RUN_OPTIONS, \
    BOTLEAGUE_INNER_RESULTS_DIR_NAME, JOB_STATUS_ASSIGNED, JOB_TYPE_EVAL, \
    JOB_TYPE_SIM_BUILD
from problem_constants import constants

from constants import SIM_IMAGE_BASE_TAG
from logs import add_stackdriver_sink
from utils import is_docker

container_run_level = log.level('CONTAINER', no=10, color='<magenta>')

DIR = os.path.dirname(os.path.realpath(__file__))


def safe_box_update(box_to_update, **fields):
    # https://github.com/cdgriffith/Box/issues/98
    box_to_update = box_to_update.to_dict()
    box_to_update.update(**fields)
    box_to_update = Box(box_to_update)
    return box_to_update


class Worker:
    def __init__(self, jobs_db=None, instances_db=None, run_problem_only=False):
        self.instance_id, self.is_on_gcp = fetch_instance_id()
        self.docker = docker.from_env()
        self.jobs_db = jobs_db or get_jobs_db()

        # Use this sparingly. Event loop should do most of the management
        # of instances so as to avoid race conditions.
        self.instances_db = instances_db or get_worker_instances_db()

        self.auto_updater = AutoUpdater(self.is_on_gcp)
        self.run_problem_only = run_problem_only
        self.loggedin_to_docker = False
        add_stackdriver_sink(log, self.instance_id)

    def loop(self, max_iters=None):
        iters = 0
        log.info('Worker started, checking for jobs...')
        while True:
            if self.auto_updater.updated():
                # We will be auto restarted by systemd with new code
                log.success('Ending loop, so that we are restarted with '
                            'changes')
                return
            self.stop_old_containers_if_running()
            job = self.check_for_jobs()
            if job:
                if job.status == JOB_STATUS_ASSIGNED:
                    self.mark_job_running(job)
                    if job.job_type == JOB_TYPE_EVAL:
                        self.run_eval_job(job)
                    elif job.job_type == JOB_TYPE_SIM_BUILD:
                        self.run_ci_job(job)
                    self.mark_job_finished(job)

            # TODO: Send heartbeat every minute? We'll be restarted after
            #  and idle or job timeout, so not that big of a deal.

            # TODO: Clean up containers and images with LRU and depending on
            #  disk space. Shouldn't matter until more problems and providers
            #  are added.
            iters += 1
            if max_iters is not None and iters >= max_iters:
                # Used for testing
                return job

            # Sleep with random splay to avoid thundering herd
            time.sleep(0.5 + random())

    def check_for_jobs(self) -> Box:
        # TODO: Avoid polling by creating a Firestore watch and using a
        #   mutex to avoid multiple threads processing the watch.
        job_query = self.jobs_db.collection.where(
            'instance_id', '==', self.instance_id).where(
            'status', '==', JOB_STATUS_ASSIGNED)
        jobs = list(job_query.stream())
        ret = Box()
        if len(jobs) > 1:
            # We currently only support one job per instance
            raise RuntimeError('Got more than one job for instance')
        elif not jobs:
            log.debug('No job for instance in db')
        else:
            ret = Box(jobs[0].to_dict())
        return ret

    def mark_job_finished(self, job):
        # We've added results to the job so disable compare_and_swap
        # The initial check to mark running will be enough to
        # to prevent multiple runners.
        job.status = JOB_STATUS_FINISHED
        job.finished_at = SERVER_TIMESTAMP
        self.jobs_db.set(job.id, job)

    def mark_job_running(self, job):
        self.set_job_atomic(job,
                            status=JOB_STATUS_RUNNING,
                            started_at=SERVER_TIMESTAMP)

    def set_job_atomic(self, job, **fields):
        old_job = deepcopy(job)
        job = safe_box_update(job, **fields)
        if not self.jobs_db.compare_and_swap(job.id, old_job, job):
            new_job = self.jobs_db.get(job.id)
            raise RuntimeError(f'Job status transaction failed, '
                               f'expected '
                               f'{old_job.to_json(indent=2, sort_keys=True)}\n'
                               f'got '
                               f'{new_job.to_json(indent=2, sort_keys=True)}')

    def run_ci_job(self, job):
        secrets = get_secrets_db()
        docker_creds = secrets.get('DEEPDRIVE_DOCKER_CREDS_encrypted')
        docker_username = decrypt_symmetric(docker_creds['username'])
        docker_password = decrypt_symmetric(docker_creds['password'])
        sim_base_image = self.get_image(SIM_IMAGE_BASE_TAG, docker_username,
                                        docker_password)
        aws_creds = secrets.get('DEEPDRIVE_AWS_CREDS_encrypted')
        aws_key_id = decrypt_symmetric(aws_creds['AWS_ACCESS_KEY_ID'])
        aws_secret = decrypt_symmetric(aws_creds['AWS_SECRET_ACCESS_KEY'])
        container_args = dict(docker_tag=SIM_IMAGE_BASE_TAG,
                              env=dict(
                                  DEEPDRIVE_COMMIT=job.commit,
                                  DEEPDRIVE_BRANCH=job.branch,
                                  AWS_ACCESS_KEY_ID=aws_key_id,
                                  AWS_SECRET_ACCESS_KEY=aws_secret,
                              ))
        containers, success = self.run_containers([container_args])
        results = Box(
            logs=Box(),
            errors=Box(),
            sim_base_docker_digest=sim_base_image.attrs['RepoDigests'][0],
        )
        self.set_container_logs_and_errors(containers=containers,
                                           results=results, job=job)
        job.results = results  # These are saved when the job is marked finished

    def run_eval_job(self, job):
        # TODO: Support N bot and N problem containers
        eval_spec = job.eval_spec

        problem_tag = f'deepdriveio/deepdrive:problem_{eval_spec.problem}'
        bot_tag = job.eval_spec.docker_tag

        problem_image = self.get_image(problem_tag)
        bot_image = self.get_image(bot_tag)

        problem_container_args, results_mount = self.get_problem_container_args(
            problem_tag, eval_spec)
        bot_container_args = dict(docker_tag=bot_tag)

        results = Box(
            logs=Box(),
            errors=Box(),
            problem_docker_digest=problem_image.attrs['RepoDigests'][0],
            bot_docker_digest=bot_image.attrs['RepoDigests'][0],)

        containers = [problem_container_args]
        if not self.run_problem_only:
            containers.append(bot_container_args)
        containers, success = self.run_containers(containers)
        self.set_container_logs_and_errors(containers=containers,
                                           results=results, job=job)
        if success:
            # Fetch eval results stored on the host by the problem container
            results.update(self.get_results(results_dir=results_mount))
        job.results = results  # These are saved when the job is marked finished

        self.send_results(job)

    def set_container_logs_and_errors(self, containers, results, job):
        for container in containers:
            image_name = container.attrs["Config"]["Image"]
            container_id = \
                f'{image_name}_{container.short_id}'
            run_logs = container.logs(timestamps=True).decode()
            log.log('CONTAINER', f'{container_id} logs begin \n' + ('-' * 80))
            log.log('CONTAINER', run_logs)
            log.log('CONTAINER', f'{container_id} logs end \n' + ('-' * 80))
            exit_code = container.attrs['State']['ExitCode']
            if exit_code != 0:
                results.errors[container_id] = f'Container failed with' \
                    f' exit code {exit_code}'
            elif container.status == 'dead':
                results.errors[container_id] = f'Container died, please retry.'

            log_url = self.upload_logs(
                run_logs, filename=f'{image_name}_job-{job.id}.txt')
            log.info(f'Uploaded logs for {container_id} to {log_url}')
            results.logs[container_id] = log_url

    def get_image(self, tag, dockerhub_username=None, dockerhub_password=None):
        log.info('Pulling docker image %s...' % tag)
        if dockerhub_username is not None and not self.loggedin_to_docker:
            self.docker.login(username=dockerhub_username,
                              password=dockerhub_password)
            self.loggedin_to_docker = True

        result = self.docker.images.pull(tag)
        log.info('Finished pulling docker image %s' % tag)
        if isinstance(result, list):
            ret = self.get_latest_docker_image(result)
            if ret is None:
                raise RuntimeError(
                    f'Could not get pull latest image for {tag}. '
                    f'tags found were: {result}')
        elif isinstance(result, Image):
            ret = result
        else:
            log.warning(f'Got unexpected result when pulling {tag} of {result}')
            ret = result
        return ret

    @staticmethod
    def get_latest_docker_image(images):
        for image in images:
            for tag in image.attrs['RepoTags']:
                if tag.endswith(':latest'):
                    return image
        return None

    def get_problem_container_args(self, tag, eval_spec):
        # TODO: Change FILEPATH to DIR in deepdrive
        result_dir = f'{BOTLEAGUE_RESULTS_DIR}/' + \
                     f'{BOTLEAGUE_INNER_RESULTS_DIR_NAME}'
        creds_path = '/mnt/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json'
        container_env = dict(
            BOTLEAGUE_EVAL_KEY=eval_spec.eval_key,
            BOTLEAGUE_SEED=eval_spec.seed,
            BOTLEAUGE_PROBLEM=eval_spec.problem,
            BOTLEAGUE_RESULT_FILEPATH=result_dir,
            DEEPDRIVE_UPLOAD='1',
            GOOGLE_APPLICATION_CREDENTIALS=creds_path
        )
        results_mount = self.get_results_mount(eval_spec)
        container = dict(docker_tag=tag,
                         env=container_env,
                         volumes={
                             results_mount: {
                                 'bind': BOTLEAGUE_RESULTS_DIR,
                                 'mode': 'rw'
                             },
                             '/root/.gcpcreds': {
                                 'bind': '/mnt/.gcpcreds',
                                 'mode': 'rw'
                             }
                         })
        return container, results_mount

    @staticmethod
    def get_results_mount(eval_spec):
        if is_docker():
            results_mount_base = '/mnt/botleague_results'
        else:
            results_mount_base = f'{DIR}/botleague_results'
        results_mount = f'{results_mount_base}/{eval_spec.eval_id}'
        os.makedirs(results_mount, exist_ok=True)
        os.system(f'chmod -R 777 {results_mount}')
        log.info(f'results mount {results_mount}')
        return results_mount

    def send_results(self, job):
        if in_test():
            return
        else:
            try:
                log.info(f'Sending results for job \n{job.to_json(indent=2)}')
                results_resp = requests.post(
                    f'{job.botleague_liaison_host}/results',
                    json=dict(eval_key=job.eval_spec.eval_key,
                              results=job.results))
                if not results_resp.ok:
                    log.error(
                        f'Error posting results back to botleague: '
                        f'{results_resp}')
                else:
                    json_resp = results_resp.json()
                    log.success(f'Successfully posted to botleague! response:\n'
                                f'{json.dumps(json_resp, indent=2)}')
            except Exception:
                # TODO: Create an alert on this log message
                log.exception('Possible problem results back to '
                              'problem endpoint.')
            finally:
                # TODO: Move this into problem-constants and rename
                #  problem-helpers as it's shared with problem-worker
                instance = self.instances_db.get(job.instance_id)
                instance.status = constants.INSTANCE_STATUS_AVAILABLE
                instance.time_last_available = SERVER_TIMESTAMP
                self.instances_db.set(job.instance_id, instance)
                log.info(f'Made instance {job.instance_id} available')

    @staticmethod
    def get_results(results_dir) -> dict:
        results = {}
        directory = f'{results_dir}/{BOTLEAGUE_INNER_RESULTS_DIR_NAME}'
        result_str = open(f'{directory}/results.json').read()
        if is_json(result_str):
            results.update(json.loads(result_str))
        else:
            results['error'] = \
                f'No results file found at {BOTLEAGUE_RESULTS_FILEPATH}'
        return results

    def run_containers(self, containers_args: list = None):
        log.info('Running containers %s...' % containers_args)
        containers = [self.start_container(**c) for c in containers_args]
        try:
            containers, success = self.monitor_containers(containers)
        except Exception as e:
            log.error(f'Exception encountered while running '
                      f'containers: {containers.to_json(indent=2)}, '
                      'stopping all containers.')
            for container in containers:
                log.error(f'Stopping orphaned container: {container}')
                container.stop(timeout=1)
            raise e
        return containers, success

    def monitor_containers(self, containers):
        success = True
        running = True
        failed = False
        dead = False
        last_timestamps = [None] * len(containers)
        last_loglines = [None] * len(containers)
        while running and not (failed or dead):
            # Refresh container status
            containers = [self.docker.containers.get(c.short_id)
                          for c in containers]

            running = [c for c in containers if c.status in
                       ['created', 'running']]

            for container_idx, container in enumerate(containers):
                last_timestamp = last_timestamps[container_idx]
                if last_timestamp is None:
                    log_lines = container.logs(timestamps=True).decode()
                    log_lines = re.split('\n', log_lines.strip())
                    # noinspection PyPep8
                    try:
                        last_timestamp = self.get_last_timestamp(log_lines)
                    except:
                        log.warning(f'Could not get timestamp from logs '
                                    f'{log_lines}')
                        last_timestamp = None
                else:
                    log_lines = container.\
                        logs(timestamps=True, since=last_timestamp).decode()
                    log_lines = re.split('\n', log_lines.strip())
                    last_logline = last_loglines[container_idx]
                    if last_logline is not None:
                        try:
                            # noinspection PyTypeChecker
                            dupe_index = log_lines.index(last_logline)
                            log_lines = log_lines[dupe_index+1:]
                        except ValueError:
                            pass

                    last_timestamp = (self.get_last_timestamp(log_lines) or
                                      last_timestamp)

                if log_lines:
                    last_loglines[container_idx] = log_lines[-1]
                    log.log('CONTAINER', '\n'.join(log_lines))
                last_timestamps[container_idx] = last_timestamp
                last_loglines[container_idx] = last_logline

            # TODO: Do a container.logs(since=last, timestamps=True) and
            #   log those in real time.

            # TODO: For N bots or N problems, we probably want to make a best
            #  effort so long as at least 1 bot and one problem are still alive.
            dead = [c for c in containers if c.status == 'dead']
            failed = [c for c in containers if c.attrs['State']['ExitCode'] > 0]

            if dead:
                success = False
                log.error(f'Dead container(s) found: {dead}')

            if failed:
                success = False
                log.error(f'Containers failed: {failed}')

            time.sleep(0.1)
        for container in running:
            log.error(f'Stopping orphaned container: {container}')
            container.stop(timeout=1)
        log.info('Finished running containers %s' % containers)
        return containers, success

    @staticmethod
    def get_last_timestamp(logs) -> Optional[datetime]:
        if not (logs and logs[0]):
            return None
        last_timestamp = \
            logs[-1].split(' ')[0]
        last_timestamp = datetime.strptime(last_timestamp[:-4],
                                           '%Y-%m-%dT%H:%M:%S.%f')
        return last_timestamp

    def start_container(self, docker_tag, cmd=None, env=None, volumes=None):
        container = self.docker.containers.run(docker_tag, command=cmd,
                                               detach=True, stdout=False,
                                               stderr=False,
                                               environment=env,
                                               volumes=volumes,
                                               **CONTAINER_RUN_OPTIONS)
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


    def stop_old_containers_if_running(self):
            containers = self.docker.containers.list()

            def is_botleague(container):
                tags = container.image.attrs['RepoTags']
                if tags:
                    image_name = tags[0]
                    if (
                        image_name.startswith('deepdriveio/deepdrive:problem_') or
                        image_name.startswith('deepdriveio/deepdrive:bot_') or
                        image_name == 'deepdriveio/private:deepdrive-sim-package'
                    ):
                        return True
                return False

            for container in containers:
                if container.status == 'running' and is_botleague(container):
                    container.stop()


def main():
    worker = Worker()
    worker.loop()


def play():
    pass
    # encrypt_db_key(get_db('secrets'), 'DEEPDRIVE_DOCKER_CREDS')


if __name__ == '__main__':
    # play()
    main()

