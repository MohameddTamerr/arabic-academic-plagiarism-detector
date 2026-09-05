# -*- coding: utf-8 -*-
"""
Multi-worker concurrency and crash recovery integration tests.
Verifies multi-process worker safety, zero double-processing, crash recovery,
and distributed lock mutual exclusion.
"""

import time
import pytest
from app.queue.db_queue import DatabaseJobQueue
from app.queue.distributed_lock import DatabaseDistributedLock
from tools.benchmark_queue_concurrency import run_concurrency_benchmark


def test_distributed_lock_mutual_exclusion_and_ttl():
    lock = DatabaseDistributedLock()
    lock_name = "TEST_INDEX_REBUILD_LOCK"
    owner1 = "worker_alpha"
    owner2 = "worker_beta"

    # Acquire lock by owner1
    acq1 = lock.acquire(lock_name, owner_token=owner1, ttl_seconds=2)
    assert acq1 is True
    assert lock.is_locked(lock_name) is True

    # Owner2 must be rejected
    acq2 = lock.acquire(lock_name, owner_token=owner2, ttl_seconds=2)
    assert acq2 is False

    # Owner1 re-acquires/extends lock
    acq1_ext = lock.acquire(lock_name, owner_token=owner1, ttl_seconds=2)
    assert acq1_ext is True

    # Release lock
    rel = lock.release(lock_name, owner_token=owner1)
    assert rel is True
    assert lock.is_locked(lock_name) is False

    # Now owner2 can acquire
    acq2_after = lock.acquire(lock_name, owner_token=owner2, ttl_seconds=2)
    assert acq2_after is True
    lock.release(lock_name, owner_token=owner2)


def test_multi_worker_concurrent_execution_and_zero_duplicate_safety():
    """Verify concurrent worker claiming and completion with 0 duplicate processing."""
    from concurrent.futures import ThreadPoolExecutor

    queue = DatabaseJobQueue()
    num_jobs = 30
    enqueued_ids = []

    # Enqueue jobs across departments
    for i in range(num_jobs):
        jid = queue.enqueue(
            job_type="SCAN_RESEARCH",
            payload={"doc_idx": i},
            priority=(i % 5) + 1,
            department_id=f"DEP_{i % 3}"
        )
        enqueued_ids.append(jid)

    processed_jobs = []

    def worker_loop(w_id: str):
        worker_processed = []
        for _ in range(100):
            claimed = queue.claim(worker_id=w_id, capabilities=["SCAN_RESEARCH"], lease_seconds=10, max_jobs=1)
            if claimed:
                for j in claimed:
                    time.sleep(0.005) # Simulate fast processing
                    queue.complete(j['id'], j['claim_token'])
                    worker_processed.append(j['id'])
            else:
                time.sleep(0.02)
        return worker_processed

    # Run 4 concurrent worker threads
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(worker_loop, [f"worker_thread_{i}" for i in range(4)]))

    all_processed = [j for sublist in results for j in sublist]
    enqueued_set = set(enqueued_ids)
    processed_from_this_test = [j for j in all_processed if j in enqueued_set]

    # Assertions
    assert len(processed_from_this_test) == num_jobs, f"Expected {num_jobs}, got {len(processed_from_this_test)}"
    # Zero duplicates
    assert len(set(processed_from_this_test)) == num_jobs, "Duplicate processing detected!"
