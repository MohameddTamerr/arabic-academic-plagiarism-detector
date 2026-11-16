"""Minimal Windows spawn target: deliberately exits without releasing its lock.

Keep application imports out: the recovery test measures a dead lock owner,
not the time required to import the full test suite in a spawned interpreter.
"""
import json
import os
import time


def crash_holder(lock_file, ready_event):
    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    payload = {'token': 'crash-token-test', 'owner': f'crashing_proc_{os.getpid()}',
               'pid': os.getpid(), 'acquired_at': time.time(),
               'expires_at': time.time() + 300}
    os.write(fd, json.dumps(payload).encode('utf-8'))
    os.close(fd)
    ready_event.set()
    os._exit(0)
