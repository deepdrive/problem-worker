import os

from constants import JOB_STATUS_TO_START, JOB_STATUS_FINISHED
from worker import EvalWorker
from common import get_eval_jobs_kv_store


def test_eval_worker():
    os.environ['FORCE_FIRESTORE_DB'] = '1'
    os.environ['INSTANCE_ID'] = '9999999999999999999'
    worker = EvalWorker()
    job_kv = get_eval_jobs_kv_store()
    job_id = 'TEST_JOB'
    test_job = job_kv.get(job_id)
    test_job.status = JOB_STATUS_TO_START
    job_kv.set(job_id, test_job)
    job = worker.loop(max_iters=1)
    assert job
    assert job.id == job.eval_spec.eval_id
    assert job.results
    assert job.results.logs
    assert job.status.lower() == JOB_STATUS_FINISHED
    del os.environ['FORCE_FIRESTORE_DB']
    assert 'FORCE_FIRESTORE_DB' not in os.environ


if __name__ == '__main__':
    test_eval_worker()
