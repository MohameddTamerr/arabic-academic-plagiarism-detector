"""Run the isolated opt-in benchmark offline and capture host memory pressure.

Run from the repository root with the same installed dependencies and verified
research assets as Stage 8H. This does not enable production AI detection.
"""
import argparse
import atexit
import ctypes
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

import psutil


def system_commit():
    if os.name != 'nt':
        return None
    class PerformanceInfo(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong)] + [(name, ctypes.c_size_t) for name in (
            'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal',
            'PhysicalAvailable', 'SystemCache', 'KernelTotal', 'KernelPaged',
            'KernelNonpaged', 'PageSize')] + [(name, ctypes.c_ulong) for name in (
            'HandleCount', 'ProcessCount', 'ThreadCount')]
    info = PerformanceInfo()
    info.cb = ctypes.sizeof(info)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
        raise ctypes.WinError()
    return {name: getattr(info, name) * info.PageSize for name in (
        'CommitTotal', 'CommitLimit', 'CommitPeak')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus', choices=['empty', 'populated'], default='empty')
    parser.add_argument('--workflow',choices=['plagiarism','research'],default='research')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / os.environ.get('STAGE8J_OUTPUT_DIR', 'scratch/stage8j')
    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'RUN_STAGE8I': '1', 'STAGE8J_PROFILE': '1',
           'STAGE8L_WORKFLOW':args.workflow,
           'STAGE8J_CORPUS': args.corpus, 'HF_HUB_OFFLINE': '1',
           'TRANSFORMERS_OFFLINE': '1'}
    samples = []
    perfmon = None
    perf_log = None
    wall_started = time.time()
    if os.name == 'nt':
        perf_log = (output / (args.corpus + '_paging.log')).open('w',encoding='utf-8')
        perfmon = subprocess.Popen(['typeperf', r'\Memory\Pages Input/sec',
            r'\Memory\Pages Output/sec', r'\Paging File(_Total)\% Usage',
            '-si','1','-y','-o',str(output/(args.corpus+'_paging.csv'))],
            stdout=perf_log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
        def close_perfmon():
            if perfmon.poll() is None:
                perfmon.terminate()
            perfmon.wait(timeout=10)
            perf_log.close()
        atexit.register(close_perfmon)
    start = time.perf_counter()
    with (output / (args.corpus + '_pytest.log')).open('w', encoding='utf-8') as log:
        child = subprocess.Popen([sys.executable, '-m', 'pytest', '-q',
            '--disable-warnings', 'tests/test_stage8i_full_system.py'],
            cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
        while child.poll() is None:
            vm = psutil.virtual_memory()
            samples.append({'elapsed': time.perf_counter() - start,
                'available_physical_bytes': vm.available,
                'system_cpu_percent': psutil.cpu_percent(),
                'system_commit': system_commit()})
            time.sleep(1)
    result = {'platform': platform.platform(), 'python': sys.version,
        'workflow':args.workflow,
        'logical_cpus': psutil.cpu_count(), 'total_ram': psutil.virtual_memory().total,
        'exit_code': child.returncode, 'elapsed': time.perf_counter() - start,
        'samples': samples, 'limitations': ['System counters include other applications',
        'Paging CSV contains whole-system Windows counters; localized counter availability must be checked; GUI responsiveness is unmeasured',
        'Synthetic corpus/documents, test client, test antivirus and authentication mode']}
    paging_path=output/(args.corpus+'_paging.csv')
    result['paging_file_updated_this_run']=paging_path.exists() and paging_path.stat().st_mtime>=wall_started
    result['paging_monitor_exit_before_stop']=perfmon.poll() if perfmon is not None else None
    (output / (args.corpus + '_host.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
    if perfmon is not None:
        close_perfmon()
        atexit.unregister(close_perfmon)
    return child.returncode


if __name__ == '__main__':
    raise SystemExit(main())
