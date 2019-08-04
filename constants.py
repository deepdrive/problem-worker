###############################################################
# WARNING: These are shared with                              #
# https://github.com/deepdrive/problem-evaluator/constants.py #
###############################################################
import os

GCP_REGION = 'us-west1'
GCP_ZONE = GCP_REGION + '-b'
GCP_PROJECT = os.environ.get('GOOGLE_CLOUD_PROJECT') or \
              os.environ.get('GCP_PROJECT', None)
INSTANCE_EVAL_LABEL = 'deepdrive-eval'
EVAL_INSTANCES_COLLECTION_NAME = 'deepdrive_eval_instances'
EVAL_JOBS_COLLECTION_NAME = 'deepdrive_eval_jobs'
EVAL_LOOP_ID = 'deepdrive_eval_loop'

# This should be public for submitters to see logs
BOTLEAGUE_LOG_BUCKET = 'deepdriveio'

BOTLEAGUE_LOG_DIR = 'botleague_eval_logs'
BOTLEAGUE_RESULTS_DIR = '/mnt/botleague'
BOTLEAGUE_RESULTS_FILEPATH = f'{BOTLEAGUE_RESULTS_DIR}/results.json'

JOB_STATUS_TO_START = 'to_start'
JOB_STATUS_RUNNING = 'running'
JOB_STATUS_FINISHED = 'finished'


RESULTS_CALLBACK = 'https://sim.deepdrive.io/eval_results'

METADATA_URL = 'http://metadata.google.internal/computeMetadata/v1/instance'
