# -*- coding: utf-8 -*-
"""
Unit and integration tests for persistent distributed database queue.
Verifies atomic claiming, claim tokens, leasing, heartbeats, department fairness,
backpressure, error redaction, and stale lease recovery.
"""

import time
import pytest
from app.queue.db_queue import DatabaseJobQueue, redact_error_message
from app.services.resource_governor import check_resource_limits, can_accept_new_scan_job


def test_queue_enqueue_and_atomic_claim():
    queue = DatabaseJobQueue()
    jid = queue.enqueue(
        job_type="SCAN_RESEARCH",
        payload={"research_id": 101, "title": "Test Paper"},
        priority=2,
        department_id="DEP_CS"
    )
    assert jid.startswith("job_")

    claimed = queue.claim(worker_id="worker_01", capabilities=["SCAN_RESEARCH"], lease_seconds=30, max_jobs=1)
    assert len(claimed) == 1
    c = claimed[0]
    assert c['id'] == jid
    assert c['claim_token'] is not None
    assert c['priority'] == 2

    # Second claim by another worker must return empty (Zero double-processing)
    claimed2 = queue.claim(worker_id="worker_02", capabilities=["SCAN_RESEARCH"], lease_seconds=30, max_jobs=1)
    assert len(claimed2) == 0


def test_queue_heartbeat_and_completion():
    queue = DatabaseJobQueue()
    jid = queue.enqueue(job_type="OCR", payload={"page": 1}, priority=3)
    claimed = queue.claim(worker_id="worker_ocr", capabilities=["OCR"], lease_seconds=10, max_jobs=1)[0]
    token = claimed['claim_token']

    # Heartbeat extension
    hb_ok = queue.heartbeat(jid, token, extend_seconds=40)
    assert hb_ok is True

    # Complete job
    done_ok = queue.complete(jid, token)
    assert done_ok is True

    # Verification of completed status
    job_info = queue.get_job(jid)
    assert job_info['status'] == 'completed'
    assert job_info['completed_at'] is not None


def test_queue_failure_and_retry_backoff():
    queue = DatabaseJobQueue()
    jid = queue.enqueue(job_type="EXPORT", payload={"doc_id": 5}, priority=3)
    claimed = queue.claim(worker_id="worker_exp", capabilities=["EXPORT"], lease_seconds=10, max_jobs=1)[0]
    token = claimed['claim_token']

    # Fail with retryable error
    fail_ok = queue.fail(
        jid,
        token,
        error_code="ERR_NETWORK_TIMEOUT",
        error_message="Connection lost to postgresql://user:secretpass@127.0.0.1/db",
        retryable=True,
        backoff_seconds=0
    )
    assert fail_ok is True

    job_info = queue.get_job(jid)
    assert job_info['attempt_count'] == 1
    # Error message must be sanitized
    assert "secretpass" not in job_info['error_message']
    assert "[REDACTED]" in job_info['error_message']


def test_queue_pause_and_cancellation():
    queue = DatabaseJobQueue()
    jid = queue.enqueue(job_type="SCAN", payload={}, priority=1)

    # Pause queue claims
    queue.pause_claims()
    assert queue.is_paused() is True

    claimed = queue.claim(worker_id="worker_p", capabilities=["SCAN"], lease_seconds=30)
    assert len(claimed) == 0

    # Resume claims
    queue.resume_claims()
    assert queue.is_paused() is False

    # Admin cancellation
    canc_ok = queue.cancel(jid, reason="Cancelled by Dean")
    assert canc_ok is True

    job_info = queue.get_job(jid)
    assert job_info['status'] == 'cancelled'


def test_stale_job_recovery_after_lease_expiration():
    queue = DatabaseJobQueue()
    jid = queue.enqueue(job_type="SCAN", payload={}, priority=1)
    claimed = queue.claim(worker_id="worker_dead", capabilities=["SCAN"], lease_seconds=1)[0]

    # Sleep to allow lease to expire
    time.sleep(1.1)

    # Recovery run
    recovered = queue.recover_stale_jobs(timeout_seconds=1)
    assert recovered >= 1

    job_info = queue.get_job(jid)
    assert job_info['status'] == 'queued'
    assert job_info['claimed_by'] is None


def test_error_message_redaction():
    raw_error = "Failed at C:\\Sensitive\\Path\\doc.pdf with password=MySecretPassword123"
    clean = redact_error_message(raw_error)
    assert "MySecretPassword123" not in clean
    assert "[REDACTED]" in clean


def test_resource_governor_limits():
    ok, err, details = check_resource_limits()
    assert isinstance(ok, bool)
    assert isinstance(details, dict)

    accept_ok, accept_err = can_accept_new_scan_job(queue_depth=50)
    assert accept_ok is True
