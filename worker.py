import json
import os
import sys

from io import StringIO
from typing import Optional

import re

from botleague_helpers.crypto import decrypt_symmetric, decrypt_db_key
from botleague_helpers import docker_cleanup
from botleague_helpers.db import get_db
from botleague_helpers.utils import box2json
from datetime import datetime

import time
from copy import deepcopy
from random import random

import requests
import docker
from box import Box, BoxList
from docker.models.images import Image
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from logs import log

from botleague_helpers.config import in_test

from auto_updater import AutoUpdater
from common import is_json, get_jobs_db, fetch_instance_id, \
    get_worker_instances_db, get_secrets_db
from problem_constants.constants import JOB_STATUS_RUNNING, \
    JOB_STATUS_FINISHED, \
    BOTLEAGUE_RESULTS_FILEPATH, BOTLEAGUE_RESULTS_DIR, BOTLEAGUE_LOG_BUCKET, \
    BOTLEAGUE_LOG_DIR, CONTAINER_RUN_OPTIONS, \
    BOTLEAGUE_INNER_RESULTS_DIR_NAME, JOB_STATUS_ASSIGNED, JOB_TYPE_EVAL, \
    JOB_TYPE_SIM_BUILD, JOB_TYPE_DEEPDRIVE_BUILD
from problem_constants import constants as prob_const

from constants import SIM_PACKAGE_IMAGE_TAG, STACKDRIVER_LOG_NAME, \
    DEEPDRIVE_BUILD_IMAGE_TAG
from botleague_helpers.logs import add_stackdriver_sink
from utils import is_docker, dbox

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
        """
        :param jobs_db: Job status, etc... in Firestore
        :param instances_db: Instance status, etc... in Firestore
        :param run_problem_only: If True, will not run the bot container. This
            is not relevant to sim-build jobs.
        """
        self.instance_id, self.is_on_gcp = fetch_instance_id()
        self.docker = docker.from_env()
        self.jobs_db = jobs_db or get_jobs_db()

        # Use this sparingly. Event loop should do most of the management
        # of instances so as to avoid race conditions.
        self.instances_db = instances_db or get_worker_instances_db()

        self.auto_updater = AutoUpdater(self.is_on_gcp)
        self.run_problem_only = run_problem_only
        self.loggedin_to_docker = False
        add_stackdriver_sink(log, f'{STACKDRIVER_LOG_NAME}-inst-{self.instance_id}')
        self.docker_creds = None

    @log.catch(reraise=True)
    def loop(self, max_iters=None):
        iters = 0
        log.info('Worker started, checking for jobs ...')
        while True:
            docker_cleanup.prune()

            # TODO: Pull in containers that we'll likely need

            if self.auto_updater.updated():
                # We will be auto restarted by systemd with new code
                log.success('Ending loop, so that we are restarted with '
                            'changes')
                return

            # TODO: Allow more than one job to run at a time.
            self.stop_old_containers_if_running()
            job = self.check_for_jobs()
            if job:
                self.run_job(job)

            # TODO: Send heartbeat every minute. Even with idle, a job without
            #  a timeout can be stuck forever if the worker process is down.
            #

            # TODO: Clean up containers and images with LRU and depending on
            #  disk space. Shouldn't matter until more problems and providers
            #  are added.

            # TODO: Use preemptible
            #  instances after docker caching is worked out.
            iters += 1
            if max_iters is not None and iters >= max_iters:
                # Used for testing
                return job

            # Sleep with random splay to avoid thundering herd
            time.sleep(0.5 + random())

    def run_job(self, job):
        log.success(f'Running job: '
                    f'{box2json(job)}')
        self.login_to_docker()
        self.mark_job_running(job)
        job.results = Box(logs=Box(), errors=Box(),)
        try:
            if job.job_type == JOB_TYPE_EVAL:
                self.run_eval_job(job)
            elif job.job_type == JOB_TYPE_SIM_BUILD:
                self.run_build_job(job)
            elif job.job_type == JOB_TYPE_DEEPDRIVE_BUILD:
                self.run_deepdrive_build_job(job)
        except Exception:
            self.handle_job_exception(job)
        self.make_instance_available(self.instances_db, job.instance_id)
        self.mark_job_finished(job)
        log.success(f'Finished job: '
                    f'{box2json(job)}')

    @staticmethod
    def handle_job_exception(job):
        """Exceptions that happen outside of the containers are handled here.
        These are likely "our" fault and should be investigated.
        """
        exception_sink = StringIO()
        exception_sink_ref = log.add(exception_sink)
        log.exception(f'Error running job '
                      f'{box2json(job)}')
        job.worker_error = exception_sink.getvalue()
        log.remove(exception_sink_ref)
        exception_sink.close()
        # TODO: Some form of retry if it's a network or other
        #   transient error

    @staticmethod
    def make_instance_available(instances_db, instance_id):
        # TODO: Move this into problem-constants and rename
        #  problem-helpers as it's shared with problem-worker
        instance = dbox(instances_db.get(instance_id))
        if not instance:
            log.warning('Instance does not exist, perhaps it was terminated.')
        elif instance.status != prob_const.INSTANCE_STATUS_AVAILABLE:
            instance.status = prob_const.INSTANCE_STATUS_AVAILABLE
            instance.time_last_available = SERVER_TIMESTAMP
            instances_db.set(instance_id, instance)
            log.info(f'Made instance {instance_id} available')
        else:
            log.warning(f'Instance {instance_id} already available')

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
        # We've added results to the job so don't compare_and_swap
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
            raise RuntimeError(
                f'Job status transaction failed, '
                f'expected '
                f'{box2json(old_job)}\n'
                f'got '
                f'{box2json(new_job)}')

    def run_build_job(self, job):
        results = job.results
        secrets = get_secrets_db()
        build_image = self.get_image(SIM_PACKAGE_IMAGE_TAG)
        aws_creds = secrets.get('DEEPDRIVE_AWS_CREDS_encrypted')
        aws_key_id = decrypt_symmetric(aws_creds['AWS_ACCESS_KEY_ID'])
        aws_secret = decrypt_symmetric(aws_creds['AWS_SECRET_ACCESS_KEY'])
        creds_path = '/mnt/.gcpcreds/silken-impulse-217423-8fbe5bbb2a10.json'
        container_args = dict(docker_tag=SIM_PACKAGE_IMAGE_TAG,
                              name=f'sim_build_{job.id}',
                              volumes={'/root/.gcpcreds': {
                                      'bind': '/mnt/.gcpcreds',
                                      'mode': 'rw'}},
                              env=dict(
                                  DEEPDRIVE_COMMIT=job.commit,
                                  DEEPDRIVE_BRANCH=job.branch,
                                  IS_DEEPDRIVE_SIM_BUILD='1',
                                  AWS_ACCESS_KEY_ID=aws_key_id,
                                  AWS_SECRET_ACCESS_KEY=aws_secret,
                                  GOOGLE_APPLICATION_CREDENTIALS=creds_path,))

        containers, success = self.run_containers([container_args])

        results.sim_base_docker_digest = build_image.attrs['RepoDigests'][0]

        self.set_container_logs_and_errors(containers=containers,
                                           results=results, job=job)
        job.results = results  # These are saved when the job is marked finished

    def run_eval_job(self, job):
        results = job.results
        # TODO: Support N bot and N problem containers
        eval_spec = job.eval_spec

        if dbox(eval_spec.problem_def).container_postfix:
            container_postfix = eval_spec.problem_def.container_postfix
        else:
            container_postfix = ''

        problem_tag = f'deepdriveio/deepdrive:problem_{eval_spec.problem}' \
            f'{container_postfix}'
        bot_tag = f'{job.eval_spec.docker_tag}{container_postfix}'

        problem_image = self.get_image(problem_tag)
        if problem_image is None:
            results.errors.problem_pull = 'Could not pull problem image'

        bot_image = self.get_image(bot_tag)
        if bot_image is None:
            results.errors.bot_pull = 'Could not pull bot image'

        if None not in [problem_image, bot_image]:
            problem_container_args, results_mount = \
                self.get_problem_container_args(problem_tag, eval_spec)
            bot_container_args = dict(docker_tag=bot_tag)

            results.problem_docker_digest = \
                problem_image.attrs['RepoDigests'][0]
            results.bot_docker_digest = bot_image.attrs['RepoDigests'][0]

            containers = [problem_container_args]
            if not self.run_problem_only:
                containers.append(bot_container_args)
            containers, success = self.run_containers(containers)
            self.set_container_logs_and_errors(containers=containers,
                                               results=results, job=job)
            if success:
                # Fetch eval results stored on the host by the problem container
                results.update(self.get_results(results_dir=results_mount))

            eval_data = job.eval_spec.full_eval_request
            problem_owner, problem_name = eval_data.problem_id.split('/')
            artifact_repo = 'deepdriveio/botleague'
            if not self.run_problem_only:
                # deepdriveio/botleague:bot-crizcraig-deepdrive-domain_randomization-2019-09-19_09-58-56PM_TXDIT35OK9UE8D7VY4M63DWZ1
                saved_bot_tag = f'bot-{eval_data.username}-{eval_data.botname}-{problem_owner}_' \
                    f'{problem_name}-{job.id}'
                bot_image.tag(artifact_repo, saved_bot_tag)
                log.info(f'Pushing {problem_tag} to {saved_bot_tag} ...')
                self.docker.images.push(artifact_repo, saved_bot_tag)
                log.info(f'Done pushing {problem_tag}')

            # deepdriveio/botleague:problem-deepdrive-domain_randomization-2019-09-19_09-58-56PM_TXDIT35OK9UE8D7VY4M63DWZ1
            saved_problem_tag = f'problem-{problem_owner}_{problem_name}-{job.id}'
            log.info(f'Pushing {problem_tag} to {saved_bot_tag} ...')
            problem_image.tag(artifact_repo, saved_problem_tag)
            self.docker.images.push(artifact_repo, saved_problem_tag)
            log.info(f'Done pushing {problem_tag}')


        self.send_results(job)

    def run_deepdrive_build_job(self, job):
        results = job.results
        build_image = self.get_image(DEEPDRIVE_BUILD_IMAGE_TAG)
        container_args = dict(docker_tag=DEEPDRIVE_BUILD_IMAGE_TAG,
                              name=f'deepdrive_build_{job.id}',
                              volumes={'/var/run/docker.sock': {
                                  'bind': '/var/run/docker.sock',
                                  'mode': 'rw'}},
                              env=dict(
                                  DEEPDRIVE_COMMIT=job.commit,
                                  DEEPDRIVE_BRANCH=job.branch,
                                  DOCKER_USER=self.docker_creds.username,
                                  DOCKER_PASS=self.docker_creds.password,))

        containers, success = self.run_containers([container_args])
        results.deepdrive_ci_image_digest = build_image.attrs['RepoDigests'][0]
        self.set_container_logs_and_errors(containers=containers,
                                           results=results, job=job)
        job.results = results  # These are saved when the job is marked finished

    def set_container_logs_and_errors(self, containers, results, job):
        for container in containers:
            image_name = container.attrs["Config"]["Image"]
            container_id = \
                f'{image_name}_{container.short_id}'
            run_logs = container.logs(timestamps=True).decode()
            results.json_results_from_logs = self.get_json_out(run_logs)
            log.log('CONTAINER', f'{container_id} logs begin \n' + ('-' * 80))
            log.log('CONTAINER', run_logs)
            log.log('CONTAINER', f'{container_id} logs end \n' + ('-' * 80))
            log_url = self.upload_logs(
                run_logs, filename=f'{image_name}_job-{job.id}.txt')

            exit_code = container.attrs['State']['ExitCode']
            if exit_code != 0:
                results.errors[container_id] = f'Container failed with' \
                    f' exit code {exit_code}'
                log.error(f'Container {container_id} failed with {exit_code}'
                          f' for job {box2json(job)}, logs: {log_url}')
            elif container.status == 'dead':
                results.errors[container_id] = f'Container died, please retry.'
                log.error(f'Container {container_id} died'
                          f' for job {box2json(job)}, logs: {log_url}')

            log.info(f'Uploaded logs for {container_id} to {log_url}')
            results.logs[container_id] = log_url

    @staticmethod
    def get_json_out(run_logs) -> str:
        json_out_delimiter = '|~__JSON_OUT_LINE_DELIMITER__~|'
        json_out_start = run_logs.find(json_out_delimiter)
        if json_out_start == -1:
            return ''
        else:
            json_out_end = run_logs.find('\n', json_out_start)
            json_out_start += len(json_out_delimiter)
            json_out = run_logs[json_out_start:json_out_end].strip()
            log.success(f'Found json out: {json_out}')
            return json_out

    def get_image(self, tag):
        log.info('Pulling docker image %s ...' % tag)
        try:
            result = self.docker.images.pull(tag)
        except:
            log.exception(f'Could not pull {tag}')
            ret = None
        else:
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
                log.warning(f'Got unexpected result when pulling {tag} '
                            f'of {result}')
                ret = result
        return ret

    def login_to_docker(self):
        if not self.loggedin_to_docker:
            creds = decrypt_db_key('DEEPDRIVE_DOCKER_CREDS')
            self.docker.login(username=creds.username,
                              password=creds.password)
            self.loggedin_to_docker = True
            self.docker_creds = creds

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
        container_env = Box(
            BOTLEAGUE_EVAL_KEY=eval_spec.eval_key,
            BOTLEAGUE_SEED=eval_spec.seed,
            BOTLEAUGE_PROBLEM=eval_spec.problem,
            BOTLEAGUE_RESULT_FILEPATH=result_dir,
            DEEPDRIVE_UPLOAD='1',
            GOOGLE_APPLICATION_CREDENTIALS=creds_path)
        if dbox(eval_spec.problem_def).problem_ci_replace_sim_url:
            container_env.SIM_URL = \
                eval_spec.problem_def.problem_ci_replace_sim_url

        # TODO: Just pass the whole eval_spec by copying/mounting a json file
        #  into the container

        results_mount = self.get_results_mount(eval_spec)
        container = dict(docker_tag=tag,
                         env=container_env.to_dict(),
                         name=f'problem_eval_id_{eval_spec.eval_id}',
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
            # For local, native testing
            results_mount_base = f'{DIR}/botleague_results'
        results_mount = f'{results_mount_base}/{eval_spec.eval_id}'
        os.makedirs(results_mount, exist_ok=True)
        os.system(f'chmod -R 777 {results_mount}')
        log.info(f'results mount {results_mount}')
        return results_mount

    @staticmethod
    def send_results(job):
        if in_test():
            return
        else:
            try:
                log.info(f'Sending results for job \n'
                         f'{box2json(job)}')
                results_resp = post_results_with_retries(
                    url=f'{job.botleague_liaison_host}/results',
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
                log.exception('Possible problem sending results back to '
                              'problem endpoint.')

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
        log.info('Running containers %s ...' % containers_args)
        containers = [self.start_container(**c) for c in containers_args]
        try:
            containers, success = self.monitor_containers(containers)
        except Exception as e:
            log.error(f'Exception encountered while running '
                      f'containers: '
                      f'{box2json(BoxList(containers))}, '
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
                # TODO: logger.add("special.log", level='CONTAINER')
                #  then use frontail to stream it from the server
                last_timestamp = last_timestamps[container_idx]
                if last_timestamp is None:
                    log_lines = container.logs(timestamps=True).decode()
                    log_lines = re.split('\n', log_lines.strip())
                    last_timestamp = self.get_last_timestamp(log_lines)
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
                    # noinspection PyTypeChecker
                    last_loglines[container_idx] = log_lines[-1]
                    log.log('CONTAINER', '\n'.join(log_lines))
                last_timestamps[container_idx] = last_timestamp

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
        try:
            last_timestamp = \
                logs[-1].split(' ')[0]
            last_timestamp = datetime.strptime(last_timestamp[:-4],
                                               '%Y-%m-%dT%H:%M:%S.%f')
        except:
            log.exception(f'Could not parse time stamp from log line: {logs[-1]}')
            last_timestamp = None
        return last_timestamp

    def start_container(self, docker_tag, cmd=None, env=None, volumes=None,
                        name=None):
        container = self.docker.containers.run(docker_tag,
                                               command=cmd,
                                               detach=True,
                                               stdout=False,
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

        def is_botleague(_container):
            tags = _container.image.attrs['RepoTags']
            if tags:
                image_name = tags[0]
                if (
                    image_name.startswith('deepdriveio/deepdrive:problem_') or
                    image_name.startswith('deepdriveio/deepdrive:bot_') or
                    image_name == 'deepdriveio/private:deepdrive-sim-package' or
                    image_name == 'deepdriveio/ue4-deepdrive-deps:latest'
                ):
                    return True
            return False

        for container in containers:
            if container.status == 'running' and is_botleague(container) and \
                    not in_test():
                container.stop()


def post_results_with_retries(max_attempts=5, **kwargs):
    done = False
    valid_results_codes = [200, 400, 500]
    attempts = 0
    resp = None
    while not done:
        resp = requests.post(**kwargs)
        if resp.status_code in valid_results_codes:
            done = True
        elif attempts < max_attempts:
            log.error(f'Failed posting results, response {resp}, retrying')
            time.sleep(1)
        else:
            done = True
        attempts += 1

    return resp


@log.catch(reraise=True)
def main():
    worker = Worker()
    worker.loop()


def play():
    # sink = StringIO()
    # sink_ref = log.add(sink)
    # log.info('asdf')
    # log.remove(sink_ref)
    # print(sink.getvalue())
    print(post_results_with_retries(url='http://127.0.0.1:5000/'))
    pass
    # encrypt_db_key(get_db('secrets'), 'DEEPDRIVE_DOCKER_CREDS')


if __name__ == '__main__':
    if 'play' in sys.argv:
        play()
    else:
        main()

