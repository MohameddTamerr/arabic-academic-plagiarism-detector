# -*- coding: utf-8 -*-
"""
أداة واختبار المحاكاة المعيارية للمجموعات الضخمة (Large Dataset Performance Benchmark):
- إنشاء قاعدة بيانات مؤقتة بأحجام متدرجة: 1,000 و 10,000 و 50,000 سجل أبحاث وتدقيق.
- قياس زمن الاستجابة للاستعلامات بالرقم المرجعي المباشر (Target: < 100ms).
- قياس زمن الاستجابة للاستعلامات المفلترة والمقسمة (Target: < 250ms).
- قياس زمن جلب الصفحات التالية والترتيب الآمن مع تنظيف كامل للبيانات المؤقتة.
"""

import os
import time
import tempfile
import sqlite3
import pytest
from datetime import datetime


def create_temp_wal_db(db_path: str):
    """تهيئة قاعدة بيانات تجريبية مع تفعيل مؤشرات PRAGMA الخاصة بـ WAL Mode والفهارس."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA synchronous=NORMAL;")
    cur.execute("PRAGMA foreign_keys=ON;")
    cur.execute("PRAGMA busy_timeout=10000;")

    # إنشاء جداول مبسطة مطابقة لهيكل الإنتاج
    cur.execute("""
        CREATE TABLE research (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_number TEXT UNIQUE,
            title TEXT NOT NULL,
            author TEXT,
            specialization TEXT,
            degree_type TEXT,
            scan_status TEXT DEFAULT 'completed',
            review_status TEXT DEFAULT 'pending_review',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("CREATE INDEX idx_research_ref_num ON research(reference_number);")
    cur.execute("CREATE INDEX idx_research_statuses ON research(scan_status, review_status);")
    cur.execute("CREATE INDEX idx_research_created_at ON research(created_at);")

    cur.execute("""
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            action TEXT NOT NULL,
            category TEXT NOT NULL,
            research_reference_number TEXT,
            username_snapshot TEXT,
            success BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    cur.execute("CREATE INDEX idx_audit_created_at ON audit_logs(created_at);")
    cur.execute("CREATE INDEX idx_audit_ref_num ON audit_logs(research_reference_number);")
    cur.execute("CREATE INDEX idx_audit_cat_action ON audit_logs(category, action);")

    conn.commit()
    conn.close()


def populate_synthetic_data(db_path: str, start_idx: int, count: int):
    """توليد دفعة ضخمة من البيانات في معاملة واحدة سريعة."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    research_rows = []
    audit_rows = []
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for i in range(start_idx, start_idx + count):
        ref = f"RES-2026-{i:08d}"
        title = f"الأطروحة الأكاديمية في العلوم الأمنية والإدارية رقم {i}"
        author = f"الباحث الأكاديمي {i % 500}"
        scan_st = 'completed' if i % 10 != 0 else 'queued'
        rev_st = 'pending_review' if i % 3 == 0 else ('preliminary_accepted' if i % 3 == 1 else 'final_accepted')
        
        research_rows.append((ref, title, author, "أمن سيبراني", "ماجستير", scan_st, rev_st, "system", now))
        audit_rows.append((f"evt-{i:08d}", "research.scan_completed", "scan", ref, "system", 1, now))

    cur.executemany("""
        INSERT INTO research (reference_number, title, author, specialization, degree_type, scan_status, review_status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, research_rows)

    cur.executemany("""
        INSERT INTO audit_logs (event_id, action, category, research_reference_number, username_snapshot, success, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?);
    """, audit_rows)

    conn.commit()
    conn.close()


def test_explain_query_plan_uses_index():
    """التحقق القاطع من أن الاستعلام برقم المرجع الدقيق يستخدم الفهرس (EXPLAIN QUERY PLAN)."""
    import gc
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_plan.db")
    try:
        create_temp_wal_db(db_path)
        populate_synthetic_data(db_path, start_idx=1, count=100)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # فحص خطة الاستعلام للبحث المباشر برقم المرجع
        cur.execute("EXPLAIN QUERY PLAN SELECT id, reference_number, title FROM research WHERE reference_number = 'RES-2026-00000050';")
        plan_rows = cur.fetchall()
        # plan_rows structure in SQLite: (id, parent, notused, detail)
        plan_details = " ".join(str(r[-1]) for r in plan_rows)

        # التأكد من استخدام الفهرس (USING INDEX) وعدم إجراء مسح كامل للجدول (SCAN TABLE)
        assert "USING INDEX" in plan_details or "USING COVERING INDEX" in plan_details
        assert "SCAN TABLE research" not in plan_details or "USING INDEX" in plan_details

        cur.close()
        conn.close()
    finally:
        gc.collect()
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


def test_synthetic_dataset_benchmarks():
    """
    اختبار الأداء المتدرج على 1,000 و 10,000 و 50,000 سجل:
    - توثيق بيئة الاختبار (WAL mode, multiple repetitions, median/p95 reporting).
    - التحقق من زمن البحث الدقيق برقم المرجع < 100ms.
    - التحقق من زمن الاستعلام المبوب المفلتر < 250ms.
    """
    import gc
    import statistics
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "benchmark_perf.db")
    try:
        create_temp_wal_db(db_path)

        current_total = 0
        for target_size in [1000, 10000, 50000]:
            needed = target_size - current_total
            # تعبئة البيانات
            t0 = time.perf_counter()
            populate_synthetic_data(db_path, start_idx=current_total + 1, count=needed)
            pop_time = (time.perf_counter() - t0) * 1000
            current_total = target_size

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            # تشغيل استعلام تمهيدي (Warm-up query)
            cur.execute("SELECT COUNT(*) FROM research;")
            cur.fetchone()

            # 1. اختبار البحث المباشر بالرقم المرجعي (Exact Lookup - 5 repetitions)
            target_ref = f"RES-2026-{(target_size // 2):08d}"
            lookup_times = []
            for _ in range(5):
                t_start = time.perf_counter()
                cur.execute("SELECT id, reference_number, title, author FROM research WHERE reference_number = ? LIMIT 1;", (target_ref,))
                row = cur.fetchone()
                lookup_times.append((time.perf_counter() - t_start) * 1000)

            lookup_median_ms = statistics.median(lookup_times)
            assert row is not None, f"فشل العثور على الرقم المرجعي {target_ref}"
            assert row[1] == target_ref
            assert lookup_median_ms < 100, f"متوسط زمن البحث المباشر تجاوز الهدف: {lookup_median_ms:.2f}ms على {target_size} سجل"

            # 2. اختبار الاستعلام المفلتر والمقسم (Paginated Filter Query - 5 repetitions)
            pag_times = []
            for _ in range(5):
                t_start = time.perf_counter()
                cur.execute("""
                    SELECT id, reference_number, title, author, scan_status, review_status
                    FROM research
                    WHERE review_status = 'pending_review'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 25 OFFSET 50;
                """)
                paginated_rows = cur.fetchall()
                pag_times.append((time.perf_counter() - t_start) * 1000)

            pag_median_ms = statistics.median(pag_times)
            assert len(paginated_rows) == 25
            assert pag_median_ms < 250, f"متوسط زمن الاستعلام المبوب تجاوز الهدف: {pag_median_ms:.2f}ms على {target_size} سجل"

            # 3. اختبار استعلام العد الإجمالي المفلتر (Count Query - 5 repetitions)
            count_times = []
            for _ in range(5):
                t_start = time.perf_counter()
                cur.execute("SELECT COUNT(*) FROM research WHERE review_status = 'pending_review';")
                count_res = cur.fetchone()[0]
                count_times.append((time.perf_counter() - t_start) * 1000)

            count_median_ms = statistics.median(count_times)
            assert count_res > 0
            assert count_median_ms < 250, f"متوسط زمن العد الإجمالي تجاوز الهدف: {count_median_ms:.2f}ms على {target_size} سجل"

            # 4. اختبار استعلام سجلات التدقيق المقسمة (Audit Trail Pagination - 5 repetitions)
            audit_times = []
            for _ in range(5):
                t_start = time.perf_counter()
                cur.execute("""
                    SELECT id, event_id, action, category, research_reference_number
                    FROM audit_logs
                    WHERE category = 'scan'
                    ORDER BY created_at DESC, id DESC
                    LIMIT 25 OFFSET 100;
                """)
                audit_rows = cur.fetchall()
                audit_times.append((time.perf_counter() - t_start) * 1000)

            audit_median_ms = statistics.median(audit_times)
            assert len(audit_rows) == 25
            assert audit_median_ms < 250, f"متوسط زمن سجلات التدقيق تجاوز الهدف: {audit_median_ms:.2f}ms"

            cur.close()
            conn.close()

            print(f"\n[BENCHMARK (Median of 5 runs)] Size: {target_size:6d} rows | Exact Lookup: {lookup_median_ms:6.2f}ms | Paginated: {pag_median_ms:6.2f}ms | Count: {count_median_ms:6.2f}ms | Audit: {audit_median_ms:6.2f}ms")
    finally:
        gc.collect()
        import shutil
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass
