import os

from botleague_helpers.db import get_db
from box import Box

import utils
from problem_constants.constants import JOB_STATUS_FINISHED, JOB_STATUS_ASSIGNED
from worker import EvalWorker


def test_worker(problem='problem-worker-test',
                bot_tag='deepdriveio/deepdrive:problem_problem-worker-test',
                run_problem_only=False):
    os.environ['FORCE_FIRESTORE_DB'] = '1'

    instance_id = '9999999999999999999'
    os.environ['INSTANCE_ID'] = instance_id

    test_id = utils.generate_rand_alphanumeric(32)
    test_jobs_collection = 'test_jobs_' + test_id
    jobs_db = get_db(test_jobs_collection, use_boxes=True,
                     force_firestore_db=True)

    job_id = 'TEST_JOB_' + utils.generate_rand_alphanumeric(32)

    test_job = Box({
        'results_callback': 'https://sim.deepdrive.io/results/domain_randomization',
        'status': JOB_STATUS_ASSIGNED,
        'id': job_id,
        'instance_id': instance_id,
        'eval_spec': {
            'docker_tag': bot_tag,
            'eval_id': job_id,
            'eval_key': 'fake_eval_key',
            'seed': 1,
            'problem': problem,
            'pull_request': None}})

    try:
        jobs_db.set(job_id, test_job)
        worker = EvalWorker(jobs_db=jobs_db, run_problem_only=run_problem_only)
        job = worker.loop(max_iters=1)
        assert job
        assert job.id == job.eval_spec.eval_id
        assert job.results
        assert job.results.logs
        assert job.status.lower() == JOB_STATUS_FINISHED
        del os.environ['FORCE_FIRESTORE_DB']
        assert 'FORCE_FIRESTORE_DB' not in os.environ
    finally:
        jobs_db.delete_all_test_data()


def test_stop_old_jobs():
    worker = EvalWorker()
    worker.stop_old_jobs_if_running()


if __name__ == '__main__':
    # test_worker('deepdriveio/deepdrive:bot_domain_randomization')
    test_worker('domain_randomization',
                bot_tag='deepdriveio/deepdrive:bot_domain_randomization')
    # test_worker(problem='problem-worker-test', run_problem_only=True)
    # test_stop_old_jobs()
