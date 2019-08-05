from google.cloud import logging as gcloud_logging
import loguru

stackdriver_client = gcloud_logging.Client()

"""
Stackdriver severities
DEFAULT	(0) The log entry has no assigned severity level.
DEBUG	(100) Debug or trace information.
INFO	(200) Routine information, such as ongoing status or performance.
NOTICE	(300) Normal but significant events, such as start up, shut down, or a configuration change.
WARNING	(400) Warning events might cause problems.
ERROR	(500) Error events are likely to cause problems.
CRITICAL	(600) Critical events cause more severe problems or outages.
ALERT	(700) A person must take an action immediately.
EMERGENCY	(800) One or more systems are unusable.
"""


def add_stackdriver_sink(loguru_logger, instance_id):
    stackdriver_logger = stackdriver_client.logger(
        f'instance-{instance_id}')

    def sink(message):
        record = message.record
        level = str(record['level'])
        if level == 'SUCCESS':
            severity = 'NOTICE'
        elif level == 'TRACE':
            # Nothing lower than DEBUG in stackdriver
            severity = 'DEBUG'
        elif level == 'EXCEPTION':
            severity = 'ERROR'
        else:
            severity = level
        stackdriver_logger.log_text(message, severity=severity)

    loguru_logger.add(sink)
