import sqlite3
import threading
import time

import pytest
from app.services import scan_service
from app.single_exe.app_controller import AppController


@pytest.fixture
def controlled(monkeypatch, tmp_path):
    executor = scan_service.DrainingScanExecutor(max_workers=1)
    monkeypatch.setattr(scan_service, '_EXECUTOR', executor)
    monkeypatch.setenv('APP_SHUTDOWN_TIMEOUT_SECONDS', '.08')
    c = AppController(host='127.0.0.1', num_workers=0)
    c.config_dir = tmp_path
    c._worker_stop_file = tmp_path / 'stop'
    c.pid_file = tmp_path / 'pid'; c.lock_file = tmp_path / 'lock'
    c.pid_file.touch(); c.lock_file.touch()
    c.db_path = tmp_path / 'test.db'
    with sqlite3.connect(c.db_path) as db:
        db.execute('create table evidence(value text)')
    release = threading.Event()
    yield c, executor, release
    release.set()
    executor.shutdown(wait=True)


def test_no_active_scans_and_repeat_stop(controlled):
    c, executor, release = controlled
    c.stop(); c.stop()
    assert c.shutdown_status == 'complete'
    assert not c.lock_file.exists()


def test_stalled_scan_deadline_retry_restart_and_integrity(controlled):
    c, executor, release = controlled
    entered = threading.Event()
    def scan():
        entered.set(); release.wait()
        with sqlite3.connect(c.db_path) as db:
            db.execute('insert into evidence values (?)', ('finished',))
    future = executor.submit(scan)
    assert entered.wait(2)
    try:
        for _ in range(2):
            before = time.monotonic()
            with pytest.raises(TimeoutError, match='still active'):
                c.stop()
            assert time.monotonic() - before < 1
            assert c.shutdown_status == 'incomplete'
            assert 'Retry' in c.shutdown_detail
            assert not future.done() and c.lock_file.exists() and c.pid_file.exists()
            with pytest.raises(RuntimeError, match='still draining'):
                c.start(auto_open_browser=False)
            with pytest.raises(RuntimeError, match='still draining'):
                scan_service.resume_scan_executor()
            with sqlite3.connect(c.db_path) as db:
                assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
                assert db.execute('select count(*) from evidence').fetchone()[0] == 0
    finally:
        release.set()
    future.result(timeout=2)
    c.stop()
    assert c.shutdown_status == 'complete' and not c.lock_file.exists()
    with sqlite3.connect(c.db_path) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert db.execute('select value from evidence').fetchone()[0] == 'finished'
    scan_service.resume_scan_executor()
    assert scan_service._EXECUTOR.submit(lambda: 42).result(timeout=2) == 42
    scan_service._EXECUTOR.shutdown(wait=True)


def test_active_scan_finishes_within_deadline(controlled, monkeypatch):
    c, executor, release = controlled
    monkeypatch.setenv('APP_SHUTDOWN_TIMEOUT_SECONDS', '2')
    entered = threading.Event()
    future = executor.submit(lambda: (entered.set(), release.wait()))
    assert entered.wait(2)
    timer = threading.Timer(.05, release.set); timer.start()
    try: c.stop()
    finally: release.set(); timer.join()
    assert future.done() and c.shutdown_status == 'complete'


@pytest.mark.parametrize('value', ['0', '-1', 'nan', 'inf'])
def test_invalid_deadline_does_not_start_shutdown(controlled, monkeypatch, value):
    c, executor, release = controlled
    monkeypatch.setenv('APP_SHUTDOWN_TIMEOUT_SECONDS', value)
    with pytest.raises(ValueError): c.stop()
    assert c.shutdown_status == 'not_started' and c.lock_file.exists()


def test_headless_exit_handler_reports_timeout_and_allows_retry(controlled, capsys):
    import ast
    import sys
    from pathlib import Path
    c, executor, release = controlled
    tree = ast.parse((Path(__file__).parents[1] / 'app/single_exe/entrypoint.py').read_text(encoding='utf8'))
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'handle_exit')
    namespace = {'controller': c, 'sys': sys}
    exec(compile(ast.Module(body=[handler], type_ignores=[]), '<headless-handler>', 'exec'), namespace)
    entered = threading.Event()
    future = executor.submit(lambda: (entered.set(), release.wait()))
    assert entered.wait(2)
    try:
        namespace['handle_exit'](None, None)
        assert c.shutdown_status == 'incomplete'
        assert 'Retry Ctrl+C' in capsys.readouterr().out
    finally: release.set()
    future.result(timeout=2)
    with pytest.raises(SystemExit) as exc:
        namespace['handle_exit'](None, None)
    assert exc.value.code == 0 and c.shutdown_status == 'complete'
