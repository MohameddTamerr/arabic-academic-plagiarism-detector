"""Exercise controller startup/stop against loopback and test-owned processes."""
import socket
import sqlite3
import subprocess
import sys
import time
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

import config
from app.services import scan_service
from app.single_exe import app_controller


@pytest.fixture(autouse=True)
def isolated_scan_executor(monkeypatch):
    # Controller shutdown is permanent for an executor. Other tests still submit scans.
    monkeypatch.setattr(scan_service, '_EXECUTOR', scan_service._new_scan_executor())
    yield
    scan_service._EXECUTOR.shutdown(wait=True)


def test_worker_timeout_preserves_locks_and_never_forces_exit(monkeypatch, tmp_path):
    from unittest.mock import Mock
    monkeypatch.setattr(app_controller, 'get_lan_ip', lambda: '127.0.0.1')
    controller = app_controller.AppController()
    controller.config_dir = tmp_path
    controller._worker_stop_file = tmp_path / 'stop'
    controller.pid_file = tmp_path / 'pid'
    controller.lock_file = tmp_path / 'lock'
    controller.pid_file.touch(); controller.lock_file.touch()
    worker = Mock()
    worker.wait.side_effect = subprocess.TimeoutExpired('owned worker', 120)
    worker.poll.return_value = None
    controller.worker_processes = [worker]
    with pytest.raises(subprocess.TimeoutExpired): controller.stop()
    worker.terminate.assert_not_called(); worker.kill.assert_not_called()
    assert controller.lock_file.exists() and controller.pid_file.exists()
    with pytest.raises(RuntimeError, match='still draining'):
        controller.start(auto_open_browser=False)


def test_shutdown_drains_active_scan_and_request(monkeypatch, tmp_path):
    from app import create_app
    from app.services import scan_service
    monkeypatch.setattr(config, 'RETRIEVAL_INDEX_DIR', tmp_path / 'retrieval_index')
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'vendor'))
    for name in ('DATA_ROOT','DATABASE_DIR','BACKUP_DIR','LOGS_DIR','DIAGNOSTICS_DIR','CONFIG_DIR'):
        monkeypatch.setattr(config, name, tmp_path / name, raising=False)
    monkeypatch.setattr(app_controller, 'get_lan_ip', lambda: '127.0.0.1')
    entered, release, response_entered, response_release = [threading.Event() for _ in range(4)]
    original_pipeline = scan_service._execute_scan_pipeline
    def pipeline(*args, **kwargs):
        entered.set()
        assert release.wait(20)
        return original_pipeline(*args, **kwargs)
    monkeypatch.setattr(scan_service, '_execute_scan_pipeline', pipeline)
    app = create_app()
    source = config.TEMP_UPLOAD_DIR / 'shutdown-owned.txt'
    source.write_text('تتناول هذه الدراسة توثيق المصادر وتحليل النتائج العلمية. ' * 30, encoding='utf8')
    task_ids = []
    @app.route('/shutdown-test', methods=['GET'])
    def work():
        task_ids.append(scan_service.start_async_scan(str(source), 'shutdown trial', 'test',
            raw_text=source.read_text(encoding='utf8'), file_name=source.name))
        response_entered.set()
        assert response_release.wait(20)
        return 'accepted'
    monkeypatch.setattr(app_controller, 'create_app', lambda: app)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    controller = app_controller.AppController(host='127.0.0.1', port=port, num_workers=0)
    controller.db_path = config.DEFAULT_SQLITE_PATH
    monkeypatch.setattr(controller, 'start_workers', lambda: None)
    errors = []
    def invoke():
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/shutdown-test', timeout=25) as r:
                assert r.status == 200
        except Exception as exc: errors.append(exc)
    def stop():
        try: controller.stop()
        except Exception as exc: errors.append(exc)
    controller.start(auto_open_browser=False)
    request = threading.Thread(target=invoke); request.start()
    assert entered.wait(10) and response_entered.wait(10)
    shutdown = threading.Thread(target=stop); shutdown.start()
    try:
        time.sleep(.2)
        assert shutdown.is_alive() and controller.lock_file.exists()
        try: urllib.request.urlopen(f'http://127.0.0.1:{port}/api/system/ping', timeout=3)
        except urllib.error.HTTPError as exc: assert exc.code == 503
        else: raise AssertionError('Shutdown accepted new work')
        response_release.set(); request.join(5)
        assert shutdown.is_alive()  # accepted scan still blocked
    finally:
        response_release.set(); release.set()
        request.join(25); shutdown.join(25)
    assert not errors and not shutdown.is_alive()
    result = scan_service.get_scan_status(task_ids[0])
    assert result['status'] == 'completed', result
    assert result['result']['ai_analysis']['status'] == 'unavailable'
    assert not controller.server_thread.is_alive()
    assert not controller.lock_file.exists()
    with sqlite3.connect(str(controller.db_path)) as db:
        assert db.execute('pragma integrity_check').fetchone()[0] == 'ok'
    controller.start(auto_open_browser=False)
    assert controller.wait_for_ready()
    controller.stop()


def test_real_worker_cooperatively_drains_current_job(monkeypatch, tmp_path):
    from app.single_exe.worker_runner import FrozenWorkerProcess
    from app.models.queue_schema import WorkerRegistry
    from app.repositories.base_repo import get_session
    stop_file = tmp_path / 'stop'
    monkeypatch.setenv('ARABIC_WORKER_STOP_FILE', str(stop_file))
    worker = FrozenWorkerProcess(['SCAN'], worker_id='shutdown-test-worker')
    entered, release = threading.Event(), threading.Event()
    claims, completed = [], []
    def claim(**kwargs):
        claims.append(1)
        return [{'id': 'owned-job', 'job_type': 'SCAN', 'claim_token': 'owned-token'}]
    monkeypatch.setattr(worker.queue, 'claim', claim)
    monkeypatch.setattr(worker.queue, 'complete', lambda *args: completed.append(args))
    original = worker.process_job
    def gated(job):
        entered.set()
        assert release.wait(10)
        original(job)
    monkeypatch.setattr(worker, 'process_job', gated)
    thread = threading.Thread(target=worker.run)
    thread.start()
    try:
        assert entered.wait(5)
        stop_file.touch()
        assert thread.is_alive()
    finally:
        release.set(); thread.join(10)
    assert not thread.is_alive()
    assert completed == [('owned-job', 'owned-token')] and len(claims) == 1
    with get_session() as session:
        assert session.get(WorkerRegistry, worker.worker_id).status == 'OFFLINE'


def test_controller_restarts_and_releases_server_worker_and_locks(monkeypatch,tmp_path):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'vendor'))
    for name in ('DATA_ROOT','DATABASE_DIR','STORAGE_ROOT','BACKUP_DIR','LOGS_DIR','DIAGNOSTICS_DIR','CONFIG_DIR'):
        monkeypatch.setattr(config,name,tmp_path/name,raising=False)
    monkeypatch.setattr(app_controller,'get_lan_ip',lambda:'127.0.0.1')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    controller=app_controller.AppController(host='127.0.0.1',port=port,num_workers=1)
    controller.db_path=config.DEFAULT_SQLITE_PATH  # autouse fixture's isolated DB
    owned=[]
    def start_worker():
        worker=subprocess.Popen([sys.executable,'-c',
            'import time,sys; from pathlib import Path; p=Path(sys.argv[1]); '
            'exec("while not p.exists(): time.sleep(.05)")', str(controller._worker_stop_file)],
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        owned.append(worker);controller.worker_processes=[worker]
    monkeypatch.setattr(controller,'start_workers',start_worker)
    try:
        for _ in range(2):
            assert controller.start(auto_open_browser=False)
            assert urllib.request.urlopen(f'http://127.0.0.1:{port}/api/system/ping',timeout=3).status==200
            controller.stop()
            assert not controller.server_thread.is_alive()
            assert owned[-1].wait(timeout=10) is not None
            assert not controller.pid_file.exists() and not controller.lock_file.exists()
            with sqlite3.connect(str(controller.db_path)) as db:
                assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):pass
                except OSError:break
                time.sleep(.1)
            else:raise AssertionError('Waitress listener remained open after stop')
    finally:
        if controller.is_running:controller.stop()
        for worker in owned:
            if worker.poll() is None:worker.terminate();worker.wait(timeout=10)
