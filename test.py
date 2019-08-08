import os

from botleague_helpers.db import get_db
from box import Box

import utils
from constants import JOB_STATUS_TO_START, JOB_STATUS_FINISHED
from worker import EvalWorker


def test_eval_worker():
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
        'status': JOB_STATUS_TO_START,
        'id': job_id,
        'instance_id': instance_id,
        'eval_spec': {
            'docker_tag': 'deepdriveio/problem-worker-test',
            'eval_id': job_id,
            'eval_key': 'fake_eval_key',
            'seed': 1,
            'problem': 'domain_randomization',
            'pull_request': None}})

    try:
        jobs_db.set(job_id, test_job)
        worker = EvalWorker(db=jobs_db)
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


if __name__ == '__main__':
    test_eval_worker()
