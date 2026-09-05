# -*- coding: utf-8 -*-
"""
اختبار التزاحم والحمل المحلي (Local Contention & Concurrency Engineering Test):
- محاكاة عمليات متزامنة ومكثفة:
  1. رفع أبحاث وتسجيلها في قاعدة البيانات.
  2. توثيق أحداث تدقيق متزامنة.
  3. استعلامات قراءة تقارير ولوحة التحكم.
  4. توليد أرقام مرجعية متزامنة.
- قياس معدل النجاح وأخطاء الأقفال وزمن الاستجابة التقريبي.
"""

import time
import uuid
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor

from app import create_app
from app.repositories import base_repo, batch_repo, report_repo
from app.services import audit_service, reference_service


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_concurrent_mixed_workload_contention(app_instance):
    """محاكاة حمل مختلط متزامن (كتابات + قراءات + تدقيق + أرقام مرجعية) وقياس استقرار الأقفال."""
    num_workers = 12
    iterations_per_worker = 5

    successes = 0
    lock_errors = 0
    latencies = []
    lock = threading.Lock()

    def mixed_task(worker_id):
        nonlocal successes, lock_errors
        with app_instance.app_context():
            for i in range(iterations_per_worker):
                start_t = time.perf_counter()
                try:
                    op_type = i % 4
                    if op_type == 0:
                        # 1. تخصيص رقم مرجعي وحفظ بحث
                        ref_no = reference_service.get_next_research_reference()
                        r_id = batch_repo.create_research(
                            title=f"بحث متزامن w{worker_id}_i{i}_{uuid.uuid4().hex[:4]}",
                            author=f"مؤلف_{worker_id}",
                            created_by=f"user_{worker_id}"
                        )
                        assert r_id > 0
                    elif op_type == 1:
                        # 2. كتابة حدث تدقيق
                        audit_service.record_event(
                            action="contention.test_event",
                            category="test",
                            object_type="contention",
                            object_id=f"w{worker_id}_i{i}",
                            success=True,
                            metadata={"worker": worker_id, "iteration": i}
                        )
                    elif op_type == 2:
                        # 3. قراءة تقارير مع إحصائيات
                        stats = report_repo.get_reports_stats()
                        reps = report_repo.get_recent_reports(limit=5)
                        assert isinstance(stats, dict)
                        assert isinstance(reps, list)
                    else:
                        # 4. حفظ واسترجاع تقرير
                        rep_id = f"cont_rep_{worker_id}_{i}_{uuid.uuid4().hex[:4]}"
                        report_repo.save_report(
                            report_id=rep_id,
                            title="تقرير متزامن",
                            overall_pct=12.0,
                            copied_pct=8.0,
                            para_pct=4.0,
                            report_dict={'title': 'تقرير متزامن'}
                        )
                        rep = report_repo.get_report(rep_id)
                        assert rep is not None

                    elapsed = (time.perf_counter() - start_t) * 1000
                    with lock:
                        successes += 1
                        latencies.append(elapsed)

                except Exception as e:
                    with lock:
                        if 'locked' in str(e).lower() or 'busy' in str(e).lower():
                            lock_errors += 1
                        else:
                            raise e

    start_total = time.perf_counter()
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [executor.submit(mixed_task, w) for w in range(num_workers)]
        for f in futures:
            f.result()
    total_time = time.perf_counter() - start_total

    total_ops = num_workers * iterations_per_worker
    avg_latency = sum(latencies) / len(latencies) if latencies else 0

    print(f"\n[ENGINEERING CONTENTION REPORT]")
    print(f"Total Operations: {total_ops}")
    print(f"Successful Operations: {successes}")
    print(f"Lock Errors: {lock_errors}")
    print(f"Total Wall-Clock Time: {total_time:.2f}s")
    print(f"Average Operation Latency: {avg_latency:.2f}ms")

    assert successes == total_ops
    assert lock_errors == 0
