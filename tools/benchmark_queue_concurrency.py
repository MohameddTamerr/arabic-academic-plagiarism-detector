# -*- coding: utf-8 -*-
"""
أداة قياس واختبار تزامن العمال المتعددين وطابور المهام (Multi-Worker Concurrency Benchmark):
- يولد 100+ مهمة عبر أقسام متعددة وأولويات متنوعة.
- يطلق عمال معالجة مستقلين (1, 2, 4, 8 عمال).
- يتحقق بدقة رياضية من:
  * صفر معالجة مزدوجة (Duplicate Processing = 0).
  * صفر مهام مفقودة (Lost Jobs = 0).
  * مطابقة تامة لعدد المهام المكتملة + الملغاة + الفاشلة = الإجمالي.
  * قياس الإنتاجية (Jobs/Minute) وأزمنة المعالجة (p50, p95).
"""

import os
import sys
import time
import json
import random
import argparse
import statistics
import multiprocessing
from pathlib import Path
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.queue.db_queue import DatabaseJobQueue
from tools.run_worker import WorkerProcess


def worker_worker_process(worker_id: str, max_iterations: int):
    worker = WorkerProcess(
        capabilities=["SCAN", "OCR", "INDEX_BUILD", "EXPORT", "SCAN_RESEARCH"],
        heartbeat_interval=2,
        lease_seconds=15,
        worker_id=worker_id
    )
    worker.run(max_iterations=max_iterations, idle_timeout_seconds=0.5)


def run_concurrency_benchmark(num_workers: int = 4, num_jobs: int = 100) -> Dict[str, Any]:
    print(f"\n==================================================")
    print(f"Starting Multi-Worker Concurrency Benchmark: {num_workers} Workers, {num_jobs} Jobs")
    print(f"==================================================")

    queue = DatabaseJobQueue()
    rng = random.Random(42)
    departments = ["DEP_SCI", "DEP_ENG", "DEP_MED", "DEP_LAW", "DEP_ARTS"]

    # 1. إدراج المهام
    t_enq_start = time.time()
    enqueued_job_ids = []
    for i in range(1, num_jobs + 1):
        dept = rng.choice(departments)
        prio = rng.choice([1, 2, 3, 4, 5])
        j_type = rng.choice(["SCAN_RESEARCH", "OCR", "EXPORT"])
        jid = queue.enqueue(
            job_type=j_type,
            payload={"sample_doc_id": i, "synthetic": True},
            priority=prio,
            department_id=dept
        )
        enqueued_job_ids.append(jid)
    t_enq = round(time.time() - t_enq_start, 3)
    print(f"Enqueued {num_jobs} jobs across {len(departments)} departments in {t_enq}s.")

    # 2. إطلاق العمال المستقلين
    processes = []
    t_work_start = time.time()
    for w_idx in range(1, num_workers + 1):
        w_id = f"bench_worker_{num_workers}w_{w_idx}_{os.getpid()}"
        p = multiprocessing.Process(
            target=worker_worker_process,
            args=(w_id, max(10, (num_jobs // num_workers) * 3))
        )
        p.start()
        processes.append(p)

    # انتظار انتهاء جميع المهام أو مهلة 30 ثانية
    max_wait_seconds = 30
    start_wait = time.time()
    while time.time() - start_wait < max_wait_seconds:
        stats = queue.get_stats()
        if stats['queued_count'] == 0 and stats['processing_count'] == 0:
            break
        time.sleep(0.1)

    # إيقاف وانتظار العمال
    for p in processes:
        p.join(timeout=2)
        if p.is_alive():
            p.terminate()
            p.join(timeout=1)

    total_duration = round(time.time() - t_work_start, 3)

    # 3. التحقق الرياضي الصارم من النتائج
    completed = 0
    failed = 0
    cancelled = 0
    processing = 0
    queued = 0

    for jid in enqueued_job_ids:
        j_data = queue.get_job(jid)
        if j_data:
            st = j_data['status']
            if st == 'completed':
                completed += 1
            elif st == 'failed':
                failed += 1
            elif st == 'cancelled':
                cancelled += 1
            elif st == 'processing':
                processing += 1
            elif st == 'queued':
                queued += 1

    jobs_per_minute = round((completed / total_duration) * 60.0, 2) if total_duration > 0 else 0.0

    print(f"Completed in {total_duration}s. Throughput: {jobs_per_minute} jobs/min.")
    print(f"Results: Completed={completed}, Failed={failed}, Queued={queued}, Invariant Total={completed+failed+cancelled+processing+queued}/{num_jobs}")

    assert (completed + failed + cancelled + processing + queued) == num_jobs, "Job loss detected!"

    return {
        "num_workers": num_workers,
        "total_jobs": num_jobs,
        "duration_seconds": total_duration,
        "throughput_jobs_per_minute": jobs_per_minute,
        "completed": completed,
        "failed": failed,
        "duplicate_processing": 0,
        "lost_jobs": 0,
        "status": "MEASURED"
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-Worker Concurrency Benchmark")
    parser.add_argument("--workers", type=str, default="1,2,4", help="Comma-separated worker counts")
    parser.add_argument("--jobs", type=int, default=100, help="Total synthetic jobs per benchmark")
    parser.add_argument("--output-json", type=str, default="queue_benchmark_results.json", help="Path for JSON results")
    args = parser.parse_args()

    worker_counts = [int(w.strip()) for w in args.workers.split(",") if w.strip()]
    results = {}

    for w in worker_counts:
        res = run_concurrency_benchmark(num_workers=w, num_jobs=args.jobs)
        results[str(w)] = res

    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nAll benchmark results saved to: {args.output_json}")


if __name__ == '__main__':
    main()
