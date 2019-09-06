import os
import sys

from loguru import logger as log

from botleague_helpers.db import get_db
from box import Box

import utils
from problem_constants.constants import JOB_STATUS_FINISHED, \
    JOB_STATUS_ASSIGNED, JOB_TYPE_EVAL, JOB_TYPE_SIM_BUILD

from common import get_worker_instances_db
from worker import Worker


def test_build_sim():
    job = get_test_job(JOB_TYPE_SIM_BUILD)
    job.branch = 'v3_stable'
    job.commit = 'e5df918089c5e4afd986ff5a09c293b90bf96869'
    job.build_id = utils.generate_rand_alphanumeric(32)
    run_test_job(job)


def get_test_job(job_type) -> Box:
    os.environ['FORCE_FIRESTORE_DB'] = '1'
    instance_id = '9999999999999999999'
    inst_db = get_worker_instances_db()
    Worker.make_instance_available(instances_db=inst_db,
                                   instance_id=instance_id)
    os.environ['INSTANCE_ID'] = instance_id
    job_id = 'TEST_JOB_' + utils.generate_rand_alphanumeric(32)
    test_job = Box({
        'botleague_liaison_host': 'https://liaison.botleague.io',
        'status': JOB_STATUS_ASSIGNED,
        'id': job_id,
        'instance_id': instance_id,
        'job_type': job_type, })
    return test_job


def run_test_job(job, run_problem_only=False):
    test_id = utils.generate_rand_alphanumeric(32)
    test_jobs_collection = 'test_jobs_' + test_id
    jobs_db = get_db(test_jobs_collection, use_boxes=True,
                     force_firestore_db=True)
    try:
        jobs_db.set(job.id, job)
        worker = Worker(jobs_db=jobs_db, run_problem_only=run_problem_only)
        job = worker.loop(max_iters=1)
        assert job
        assert job.results
        assert job.results.logs
        assert job.status.lower() == JOB_STATUS_FINISHED
        del os.environ['FORCE_FIRESTORE_DB']
        assert 'FORCE_FIRESTORE_DB' not in os.environ
    finally:
        jobs_db.delete_all_test_data()


def run_problem_eval(
        problem='problem-worker-test',
        bot_tag='deepdriveio/deepdrive:problem_problem-worker-test',
        run_problem_only=False):

    job = get_test_job(JOB_TYPE_EVAL)

    job.eval_spec = {
            'docker_tag': bot_tag,
            'eval_id': job.id,
            'eval_key': 'fake_eval_key',
            'seed': 1,
            'problem': problem,
            'pull_request': None}

    run_test_job(job, run_problem_only)


def test_stop_old_jobs():
    worker = Worker()
    worker.stop_old_containers_if_running()


def test_domain_randomization():
    run_problem_eval('domain_randomization',
                     bot_tag='deepdriveio/deepdrive:bot_domain_randomization')


def test_dummy_container():
    run_problem_eval(problem='problem-worker-test', run_problem_only=True)


def run_all(current_module):
    log.info('Running all tests')
    num = 0
    for attr in dir(current_module):
        if attr.startswith('test_'):
            num += 1
            log.info('Running ' + attr)
            getattr(current_module, attr)()
            log.success(f'Test: {attr} ran successfully')
    return num


def main():
    test_module = sys.modules[__name__]
    if len(sys.argv) > 1:
        test_case = sys.argv[1]
        log.info('Running ' + test_case)
        getattr(test_module, test_case)()
        num = 1
        log.success(f'{test_case} ran successfully!')
    else:
        num = run_all(test_module)
    log.success(f'{num} tests ran successfully!')


if __name__ == '__main__':
    main()
