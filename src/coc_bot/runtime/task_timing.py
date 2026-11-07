"""Emit task boundaries and elapsed monotonic time for runtime monitoring."""

from contextlib import contextmanager
import time
from uuid import uuid4

from loguru import logger


@contextmanager
def measure_task(account, task):
    account = account or 'unmanaged'
    task_id = uuid4().hex
    started = time.monotonic()
    result = {'outcome': 'finished'}
    logger.info('Task start: id={} account={} task={}', task_id, account, task)
    try:
        yield result
    except BaseException:
        result['outcome'] = 'interrupted'
        raise
    finally:
        logger.info('Task timing: id={} account={} task={} outcome={} seconds={:.2f}',
                    task_id, account, task, result['outcome'], time.monotonic()-started)
