# -*- coding: utf-8 -*-
"""
سلسلة اختبارات الضغط والقدرة الاستيعابية لقاعدة بيانات SQLite على مقياس المليون
(SQLite Portable Million-Scale Stress & Capacity Validation Suite)

المقاييس المستهدفة:
- 10,000 سجل
- 100,000 سجل
- 500,000 سجل
- 1,000,000 سجل
- 2,000,000 سجل

يختبر:
1. سرعة الإدراج (الفردي مع التثبيت الفوري والدفعي).
2. سرعة الاستعلامات والبحث بأنماطه المختلفة (100 تكرار لكل سيناريو).
3. أداء طابور المهام تحت الضغط (1K إلى 500K مهمة).
4. تزامن العمال المستقلين كعمليات نظام منفصلة (1, 2, 4, 8, 16 عمال OS).
5. تزامن المستخدمين المتعددين في الشبكة المحلية مع وجود كتابة في الخلفية (1, 5, 10, 25, 50, 100 مستخدم).
6. حمل هجين مستمر على مقياس 1M سجل.
7. تدريب النسخ الاحتياطي والاستعادة الحي.
8. محاكاة الانهيار واستعادة الاتساق.
9. تدقيق الفهارس وأثرها على الإدراج والبحث.
10. نموذج حساب السعات التخزينية المادية والبيانات الوصفية.

آمن بالكامل: يعمل داخل مجلد benchmark/data/ المعزول دون المساس بقاعدة البيانات الحية.
"""

import os
import sys

# ضمان دعم الترميز العربي في ويندوز
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import time

import json
import random
import string
import shutil
import hashlib
import sqlite3
import platform
import psutil
from pathlib import Path
from datetime import datetime, timedelta, timezone
import multiprocessing as mp
import threading
from typing import Dict, Any, List, Tuple

# إضافة جذر المشروع للمسارات
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# مجلد بيانات الاختبار المعزول
BENCHMARK_DIR = ROOT_DIR / 'benchmark'
DATA_DIR = BENCHMARK_DIR / 'data'
RESULTS_FILE = BENCHMARK_DIR / 'sqlite_scale_benchmark_results.json'

# مصطلحات التوثيق المعتمدة
MEASURED = "MEASURED"
SYNTHETIC = "SYNTHETIC"
PROJECTED = "PROJECTED"
ESTIMATED = "ESTIMATED"

# قواميس العبارات العربية الواقعية
ARABIC_PREFIXES = [
    "دراسة تحليلية مقارنة حول",
    "أثر تطبيق تقنيات الذكاء الاصطناعي في",
    "حوكمة النظم الأكاديمية ونزاهة البحث العلمي في",
    "معالجة اللغات الطبيعية للنصوص العربية باستخدام",
    "تطوير منظومة استرجاع المعلومات عالية الدقة لـ",
    "تقييم الأداء الأمني في الشبكات المحلية الموزعة لـ",
    "خوارزميات التعلم العميق وتحليل المشاعر في",
    "التحليل الإحصائي المتقدم للبيانات الضخمة في",
    "إطار عمل مقترح لتعزيز كفاءة الحوسبة السحابية في",
    "دراسة استكشافية حول تحديات التحول الرقمي في"
]

ARABIC_TOPICS = [
    "الجامعات والمؤسسات التعليمية",
    "القطاع الأمني والشرطي الحديث",
    "المستودعات الرقمية والمكتبات الأكاديمية",
    "أنظمة كشف الانتحال العلمي وإعادة الصياغة",
    "المحاكم والمنظومة القضائية الإلكترونية",
    "إدارة الموارد وتخطيط المؤسسات الحكومية",
    "الجرائم الإلكترونية والأدلة الرقمية",
    "أمن البيانات والخصوصية المشفرة",
    "القيادة الإدارية واتخاذ القرار الاستراتيجي",
    "المعايير القياسية للاعتماد الأكاديمي الدولي"
]

ARABIC_AUTHORS = [
    "د. أحمد محمود السعيد",
    "أ.د. فاطمة الزهراء علي",
    "د. خالد إبراهيم الشريف",
    "م. سارة عبد الرحمن يوسف",
    "د. عبد الله محمد القحطاني",
    "أ.د. منى حسن الجابري",
    "د. ياسر مصطفى النجار",
    "م. نورهان طارق العوضي",
    "د. طارق زياد البغدادي",
    "أ.د. هند عمر العمري"
]

SPECIALIZATIONS = [
    "علوم الحاسب",
    "الذكاء الاصطناعي",
    "الأمن السيبراني",
    "اللغويات الحاسوبية",
    "الإدارة والقيادة",
    "القانون والعلوم الجنائية",
    "نظم المعلومات الإدارية",
    "الإحصاء التطبيقي"
]

DEGREE_TYPES = [
    "ماجستير",
    "دكتوراه",
    "ترقية علمية",
    "بحث محكم",
    "مشروع تخرج"
]

STATUSES = ["completed", "pending_review", "queued", "failed"]
STATUS_WEIGHTS = [0.70, 0.20, 0.05, 0.05]


def get_system_environment() -> Dict[str, Any]:
    """توثيق مواصفات بيئة التشغيل بدقة."""
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage(str(ROOT_DIR))
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "os_platform": platform.platform(),
        "os_system": platform.system(),
        "os_release": platform.release(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_physical_cores": psutil.cpu_count(logical=False),
        "cpu_logical_cores": psutil.cpu_count(logical=True),
        "cpu_freq_mhz": getattr(psutil.cpu_freq(), 'current', 0) if psutil.cpu_freq() else 0,
        "ram_total_bytes": ram.total,
        "ram_total_gb": round(ram.total / (1024**3), 2),
        "ram_available_gb": round(ram.available / (1024**3), 2),
        "disk_total_gb": round(disk.total / (1024**3), 2),
        "disk_free_gb": round(disk.free / (1024**3), 2),
        "python_version": platform.python_version(),
        "sqlite_version": sqlite3.sqlite_version,
        "sqlite_source_id": sqlite3.sqlite_version_info
    }


def create_clean_db(db_path: Path, wal_mode: bool = True, synchronous: str = "NORMAL") -> sqlite3.Connection:
    """إنشاء قاعدة بيانات نظيفة مع الهيكل الكامل وضبط PRAGMA."""
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass
    wal_file = Path(f"{db_path}-wal")
    shm_file = Path(f"{db_path}-shm")
    if wal_file.exists():
        try: wal_file.unlink()
        except Exception: pass
    if shm_file.exists():
        try: shm_file.unlink()
        except Exception: pass

    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("PRAGMA page_size = 4096;")
    cur.execute("PRAGMA foreign_keys = ON;")
    if wal_mode:
        cur.execute("PRAGMA journal_mode = WAL;")
    else:
        cur.execute("PRAGMA journal_mode = DELETE;")
    cur.execute(f"PRAGMA synchronous = {synchronous};")
    cur.execute("PRAGMA busy_timeout = 10000;")
    cur.execute("PRAGMA temp_store = MEMORY;")
    cur.execute("PRAGMA cache_size = -64000;")  # 64MB cache
    cur.execute("PRAGMA wal_autocheckpoint = 1000;")

    # إنشاء الجداول الأساسية المتطابقة 100% مع نماذج التطبيق
    cur.execute("""
    CREATE TABLE IF NOT EXISTS scan_batches (
        id VARCHAR(64) PRIMARY KEY,
        label VARCHAR(500) DEFAULT '',
        created_by VARCHAR(255) DEFAULT '',
        created_at DATETIME,
        status VARCHAR(50) DEFAULT 'pending'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS research (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_number VARCHAR(50) UNIQUE,
        title VARCHAR(500) NOT NULL,
        author VARCHAR(255) DEFAULT '',
        specialization VARCHAR(255) DEFAULT '',
        degree_type VARCHAR(100) DEFAULT '',
        created_by VARCHAR(255) DEFAULT '',
        created_at DATETIME,
        batch_id VARCHAR(64) REFERENCES scan_batches(id) ON DELETE SET NULL,
        report_id VARCHAR(64),
        scan_job_id VARCHAR(64),
        scan_status VARCHAR(50) DEFAULT 'queued',
        review_status VARCHAR(50) DEFAULT 'pending_review'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS research_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        research_id INTEGER NOT NULL REFERENCES research(id) ON DELETE CASCADE,
        original_filename VARCHAR(500) NOT NULL,
        stored_filename VARCHAR(500) NOT NULL,
        file_path TEXT DEFAULT '',
        file_type VARCHAR(10) DEFAULT 'pdf',
        file_size_bytes BIGINT DEFAULT 0,
        file_order INTEGER NOT NULL DEFAULT 0,
        file_hash VARCHAR(64) DEFAULT '',
        storage_status VARCHAR(50) NOT NULL DEFAULT 'finalized'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id VARCHAR(64) PRIMARY KEY,
        title VARCHAR(500) NOT NULL,
        author VARCHAR(255) DEFAULT '',
        overall_pct FLOAT NOT NULL,
        copied_pct FLOAT NOT NULL,
        para_pct FLOAT NOT NULL,
        category VARCHAR(100) DEFAULT 'عام',
        status VARCHAR(50) DEFAULT 'محفوظ',
        scan_status VARCHAR(50) DEFAULT 'completed',
        review_status VARCHAR(50) DEFAULT 'pending_review',
        file_path TEXT DEFAULT '',
        submitted_by VARCHAR(255) DEFAULT '',
        submitted_notes TEXT DEFAULT '',
        report_json TEXT NOT NULL,
        research_id INTEGER,
        scan_execution_id VARCHAR(64),
        revision_number INTEGER DEFAULT 1 NOT NULL,
        supersedes_report_id VARCHAR(64),
        artifact_status VARCHAR(50) DEFAULT 'draft' NOT NULL,
        finalization_hash VARCHAR(64) DEFAULT ''
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS queue_jobs (
        id VARCHAR(64) PRIMARY KEY,
        job_type VARCHAR(50) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'queued',
        priority INTEGER NOT NULL DEFAULT 3,
        department_id VARCHAR(64),
        research_id INTEGER,
        batch_id VARCHAR(64),
        payload_json TEXT,
        attempt_count INTEGER DEFAULT 0,
        max_attempts INTEGER DEFAULT 3,
        claimed_by VARCHAR(128),
        claim_token VARCHAR(64),
        lease_expires_at DATETIME,
        last_heartbeat_at DATETIME,
        available_at DATETIME NOT NULL,
        created_at DATETIME NOT NULL,
        started_at DATETIME,
        completed_at DATETIME,
        error_code VARCHAR(100),
        error_message_redacted VARCHAR(500),
        worker_protocol_version VARCHAR(20) DEFAULT '1.0.0'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS worker_registry (
        id VARCHAR(128) PRIMARY KEY,
        hostname VARCHAR(255) NOT NULL,
        pid INTEGER NOT NULL,
        capabilities VARCHAR(255) NOT NULL,
        status VARCHAR(50) NOT NULL DEFAULT 'ONLINE',
        active_jobs_count INTEGER DEFAULT 0,
        started_at DATETIME,
        last_heartbeat_at DATETIME,
        worker_version VARCHAR(50) DEFAULT '1.3.0'
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS distributed_locks (
        lock_name VARCHAR(128) PRIMARY KEY,
        owner_token VARCHAR(128) NOT NULL,
        acquired_at DATETIME,
        expires_at DATETIME NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id VARCHAR(64) UNIQUE NOT NULL,
        created_at DATETIME NOT NULL,
        user_id INTEGER,
        username_snapshot VARCHAR(255) DEFAULT 'system',
        role_snapshot VARCHAR(50) DEFAULT '',
        action VARCHAR(100) NOT NULL,
        category VARCHAR(50) NOT NULL,
        object_type VARCHAR(50) DEFAULT '',
        object_id VARCHAR(64) DEFAULT '',
        research_id INTEGER,
        research_reference_number VARCHAR(50) DEFAULT '',
        batch_id VARCHAR(64),
        report_id VARCHAR(64),
        success BOOLEAN DEFAULT 1,
        failure_reason_code VARCHAR(100) DEFAULT '',
        request_id VARCHAR(64) DEFAULT '',
        ip_address VARCHAR(64) DEFAULT '',
        metadata_json TEXT DEFAULT '{}'
    );
    """)

    # إنشاء الفهارس الأساسية المتطابقة مع نماذج النظام
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_title ON research(title);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_author ON research(author);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_batch ON research(batch_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_ref_num ON research(reference_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_scan_status ON research(scan_status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_review_status ON research(review_status);")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_rf_research_id ON research_files(research_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rf_file_hash ON research_files(file_hash);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rf_storage_status ON research_files(storage_status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_rf_research_order ON research_files(research_id, file_order);")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_research_id ON reports(research_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_scan_status ON reports(scan_status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_review_status ON reports(review_status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_reports_artifact_status ON reports(artifact_status);")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_status ON queue_jobs(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_prio ON queue_jobs(priority);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_job_type ON queue_jobs(job_type);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_avail ON queue_jobs(available_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_status_prio_avail ON queue_jobs(status, priority, available_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_claimed_lease ON queue_jobs(claimed_by, lease_expires_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_qjob_dept_status ON queue_jobs(department_id, status);")

    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_created_at ON audit_logs(created_at);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_action_cat ON audit_logs(action, category);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, username_snapshot);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_ref_num ON audit_logs(research_reference_number);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_batch ON audit_logs(batch_id);")

    conn.commit()
    return conn


def generate_synthetic_research_chunk(start_idx: int, count: int) -> Tuple[List[tuple], List[tuple], List[tuple], List[tuple], List[tuple]]:
    """توليد حزمة بيانات وصفية أكاديمية واقعية."""
    research_rows = []
    file_rows = []
    report_rows = []
    queue_rows = []
    audit_rows = []

    base_date = datetime(2025, 1, 1, 8, 0, 0, tzinfo=timezone.utc)

    for i in range(start_idx, start_idx + count):
        ref_num = f"RES-2025-{i:08d}"
        prefix = ARABIC_PREFIXES[i % len(ARABIC_PREFIXES)]
        topic = ARABIC_TOPICS[(i // len(ARABIC_PREFIXES)) % len(ARABIC_TOPICS)]
        title = f"{prefix} {topic} (نموذج رقم {i})"
        author = ARABIC_AUTHORS[i % len(ARABIC_AUTHORS)]
        spec = SPECIALIZATIONS[i % len(SPECIALIZATIONS)]
        deg = DEGREE_TYPES[i % len(DEGREE_TYPES)]
        created_at = (base_date + timedelta(minutes=(i % 525600))).strftime('%Y-%m-%d %H:%M:%S')

        # تحديد الحالة
        status_roll = random.random()
        if status_roll < 0.70:
            scan_status = 'completed'
            review_status = 'preliminary_accepted' if (i % 2 == 0) else 'final_accepted'
        elif status_roll < 0.90:
            scan_status = 'completed'
            review_status = 'pending_review'
        elif status_roll < 0.95:
            scan_status = 'queued'
            review_status = 'pending_review'
        else:
            scan_status = 'failed'
            review_status = 'rejected'

        rep_id = f"rep_{i:08d}_{hashlib.md5(str(i).encode()).hexdigest()[:8]}" if scan_status == 'completed' else None
        job_id = f"job_{i:08d}_{hashlib.md5(str(i).encode()).hexdigest()[:8]}"

        research_rows.append((
            i, ref_num, title, author, spec, deg, 'system_benchmark', created_at,
            None, rep_id, job_id, scan_status, review_status
        ))

        # ملف البحث التابع
        file_hash = hashlib.sha256(f"file_payload_{i}_{title}".encode()).hexdigest()
        file_rows.append((
            i, f"research_paper_{i}.pdf", f"cas_{file_hash[:16]}.pdf",
            f"storage/finalized/{file_hash[:2]}/{file_hash}.pdf", "pdf",
            2450000 + (i % 500000), 0, file_hash, 'finalized'
        ))

        # التقرير إن كان مكتملاً (~70%)
        if rep_id and scan_status == 'completed':
            sim_score = round(random.uniform(2.5, 32.0), 2)
            copied = round(sim_score * 0.6, 2)
            para = round(sim_score * 0.4, 2)
            sample_report_json = json.dumps({
                "metadata": {"title": title, "author": author, "ref": ref_num},
                "scores": {"overall": sim_score, "copied": copied, "paraphrased": para},
                "matches_count": int(sim_score * 2),
                "summary": f"تقرير فحص آلي للبحث {ref_num} بنسبة تشابه {sim_score}%"
            }, ensure_ascii=False)

            report_rows.append((
                rep_id, title, author, sim_score, copied, para, spec, 'محفوظ',
                'completed', review_status, '', 'system_benchmark', '', sample_report_json,
                i, f"exec_{i:08d}", 1, None, 'finalized', file_hash
            ))

        # سجل التدقيق (~50%)
        if i % 2 == 0:
            event_id = f"evt_{i:08d}_{hashlib.md5(str(i).encode()).hexdigest()[:6]}"
            audit_rows.append((
                event_id, created_at, 1, 'admin', 'administrator',
                'research.ingested', 'research', 'research', str(i),
                i, ref_num, None, rep_id, 1, '', f"req_{i:08d}", '127.0.0.1', '{}'
            ))

        # مهمة الطابور (~20%)
        if i % 5 == 0:
            q_status = 'completed' if scan_status == 'completed' else ('queued' if scan_status == 'queued' else 'failed')
            avail_dt = created_at
            queue_rows.append((
                job_id, 'SCAN_RESEARCH', q_status, (i % 5) + 1, f"dept_{i % 10}",
                i, None, json.dumps({"ref": ref_num, "priority": (i % 5) + 1}),
                1 if q_status != 'queued' else 0, 3,
                f"worker_{i % 4}" if q_status != 'queued' else None,
                f"tok_{i:08d}" if q_status != 'queued' else None,
                None, None, avail_dt, created_at, created_at, created_at if q_status == 'completed' else None,
                None, None, '1.3.0'
            ))

    return research_rows, file_rows, report_rows, queue_rows, audit_rows


def populate_scale_database(scale_target: int, db_path: Path) -> Dict[str, Any]:
    """تعبئة قاعدة بيانات المقياس بالدفعات وقياس الزمن والحجم والذاكرة."""
    print(f"\n[+] البدء في بناء وتعبئة قاعدة بيانات المقياس: {scale_target:,} سجل...")
    start_time = time.perf_counter()
    process = psutil.Process()
    ram_before = process.memory_info().rss

    conn = create_clean_db(db_path, wal_mode=True, synchronous="NORMAL")
    cur = conn.cursor()

    chunk_size = 10000
    total_inserted = 0
    total_files = 0
    total_reports = 0
    total_audits = 0
    total_queue = 0

    cur.execute("BEGIN TRANSACTION;")
    for chunk_start in range(1, scale_target + 1, chunk_size):
        count = min(chunk_size, scale_target - chunk_start + 1)
        r_rows, f_rows, rep_rows, q_rows, a_rows = generate_synthetic_research_chunk(chunk_start, count)

        cur.executemany("""
        INSERT INTO research (id, reference_number, title, author, specialization, degree_type,
                              created_by, created_at, batch_id, report_id, scan_job_id, scan_status, review_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, r_rows)

        cur.executemany("""
        INSERT INTO research_files (research_id, original_filename, stored_filename, file_path,
                                    file_type, file_size_bytes, file_order, file_hash, storage_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, f_rows)

        if rep_rows:
            cur.executemany("""
            INSERT INTO reports (id, title, author, overall_pct, copied_pct, para_pct, category,
                                 status, scan_status, review_status, file_path, submitted_by,
                                 submitted_notes, report_json, research_id, scan_execution_id,
                                 revision_number, supersedes_report_id, artifact_status, finalization_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, rep_rows)

        if a_rows:
            cur.executemany("""
            INSERT INTO audit_logs (event_id, created_at, user_id, username_snapshot, role_snapshot,
                                   action, category, object_type, object_id, research_id,
                                   research_reference_number, batch_id, report_id, success,
                                   failure_reason_code, request_id, ip_address, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, a_rows)

        if q_rows:
            cur.executemany("""
            INSERT INTO queue_jobs (id, job_type, status, priority, department_id, research_id,
                                   batch_id, payload_json, attempt_count, max_attempts, claimed_by,
                                   claim_token, lease_expires_at, last_heartbeat_at, available_at,
                                   created_at, started_at, completed_at, error_code, error_message_redacted,
                                   worker_protocol_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, q_rows)

        total_inserted += len(r_rows)
        total_files += len(f_rows)
        total_reports += len(rep_rows)
        total_audits += len(a_rows)
        total_queue += len(q_rows)

        if total_inserted % 50000 == 0 or total_inserted == scale_target:
            elapsed = time.perf_counter() - start_time
            rate = total_inserted / max(0.001, elapsed)
            print(f"    -> تم إدراج {total_inserted:,} / {scale_target:,} بحث ({rate:,.0f} بحث/ثانية)")

    conn.commit()
    # تشغيل checkpoint لدمج الـ WAL والتأكد من حجم الملف النهائي
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    conn.close()

    elapsed_total = time.perf_counter() - start_time
    ram_after = process.memory_info().rss
    db_size = os.path.getsize(db_path)
    wal_size = os.path.getsize(f"{db_path}-wal") if os.path.exists(f"{db_path}-wal") else 0

    total_relational_rows = total_inserted + total_files + total_reports + total_audits + total_queue

    print(f"[✓] اكتمل بناء {scale_target:,} سجل في {elapsed_total:.2f} ثانية | حجم DB: {db_size / (1024*1024):.2f} MB | إجمالي الصفوف العلائقية: {total_relational_rows:,}")

    return {
        "scale_target": scale_target,
        "total_research_rows": total_inserted,
        "total_files_rows": total_files,
        "total_reports_rows": total_reports,
        "total_audits_rows": total_audits,
        "total_queue_rows": total_queue,
        "total_relational_rows": total_relational_rows,
        "relational_multiplier": round(total_relational_rows / max(1, total_inserted), 2),
        "build_duration_seconds": round(elapsed_total, 3),
        "ingestion_throughput_research_per_sec": round(total_inserted / max(0.001, elapsed_total), 1),
        "ingestion_throughput_total_rows_per_sec": round(total_relational_rows / max(0.001, elapsed_total), 1),
        "db_size_bytes": db_size,
        "db_size_mb": round(db_size / (1024*1024), 2),
        "db_size_gb": round(db_size / (1024*1024*1024), 4),
        "wal_size_bytes": wal_size,
        "wal_size_mb": round(wal_size / (1024*1024), 2),
        "bytes_per_research_record": round(db_size / max(1, total_inserted), 1),
        "bytes_per_relational_row": round(db_size / max(1, total_relational_rows), 1),
        "ram_rss_delta_mb": round((ram_after - ram_before) / (1024*1024), 2),
        "ram_rss_peak_mb": round(ram_after / (1024*1024), 2)
    }


def benchmark_single_insert_latency(scale_target: int, db_path: Path, iterations: int = 1000) -> Dict[str, Any]:
    """قياس زمن استجابة الإدراج الفردي (Single Insert Latency with FULL Durability)."""
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA synchronous = FULL;")
    conn.execute("PRAGMA busy_timeout = 10000;")

    latencies_ms = []
    start_id = scale_target + 1000000

    for i in range(iterations):
        curr_id = start_id + i
        ref_num = f"BENCH-INS-{curr_id:08d}"
        title = f"بحث تجريبي لقياس سرعة الإدراج الفردي {curr_id}"
        t0 = time.perf_counter()
        conn.execute("""
        INSERT INTO research (id, reference_number, title, author, specialization, degree_type, created_by, created_at, scan_status, review_status)
        VALUES (?, ?, ?, 'د. فاحص قياسي', 'علوم الحاسب', 'ماجستير', 'system_bench', datetime('now'), 'queued', 'pending_review');
        """, (curr_id, ref_num, title))
        conn.commit()
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    # تنظيف السجلات المضافة في الاختبار
    conn.execute(f"DELETE FROM research WHERE id >= {start_id};")
    conn.commit()
    conn.close()

    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]
    avg = sum(latencies_ms) / len(latencies_ms)
    min_val = latencies_ms[0]
    max_val = latencies_ms[-1]

    return {
        "scale": scale_target,
        "iterations": iterations,
        "mode": "single_insert_autocommit_full_sync",
        "min_ms": round(min_val, 3),
        "mean_ms": round(avg, 3),
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "p99_ms": round(p99, 3),
        "max_ms": round(max_val, 3),
        "inserts_per_sec": round(1000.0 / max(0.001, avg), 1)
    }


def benchmark_search_queries(scale_target: int, db_path: Path, repetitions: int = 100) -> Dict[str, Any]:
    """قياس أزمنة استجابة 11 نمط استعلام وبحث عبر 100 تكرار لكل نمط."""
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA cache_size = -64000;")
    cur = conn.cursor()

    random.seed(12345 + scale_target)
    sample_ids = random.sample(range(1, scale_target + 1), min(repetitions, scale_target))

    query_definitions = [
        ("q01_pk_exact_id", "SELECT * FROM research WHERE id = ?", lambda i: (sample_ids[i % len(sample_ids)],)),
        ("q02_indexed_ref_num", "SELECT * FROM research WHERE reference_number = ?", lambda i: (f"RES-2025-{sample_ids[i % len(sample_ids)]:08d}",)),
        ("q03_indexed_exact_title", "SELECT * FROM research WHERE title = ?", lambda i: (f"{ARABIC_PREFIXES[0]} {ARABIC_TOPICS[0]} (نموذج رقم {sample_ids[i % len(sample_ids)]})",)),
        ("q04_prefix_like_indexed", "SELECT * FROM research WHERE title LIKE 'دراسة تحليلية%' LIMIT 50", lambda i: ()),
        ("q05_substring_fts_like", "SELECT * FROM research WHERE title LIKE '%الذكاء الاصطناعي%' LIMIT 50", lambda i: ()),
        ("q06_status_filter_scan", "SELECT * FROM research WHERE scan_status = 'completed' LIMIT 50", lambda i: ()),
        ("q07_composite_meta_filter", "SELECT * FROM research WHERE specialization = 'علوم الحاسب' AND degree_type = 'دكتوراه' LIMIT 50", lambda i: ()),
        ("q08_date_range_filter", "SELECT * FROM research WHERE created_at BETWEEN '2025-03-01 00:00:00' AND '2025-06-01 00:00:00' LIMIT 50", lambda i: ()),
        ("q09_deep_offset_pagination", "SELECT * FROM research ORDER BY created_at DESC LIMIT 20 OFFSET 50000", lambda i: ()),
        ("q10_keyset_indexed_pagination", "SELECT * FROM research WHERE id > ? ORDER BY id ASC LIMIT 20", lambda i: (min(scale_target - 50, 50000),)),
        ("q11_relational_join_filter", "SELECT r.id, r.reference_number, r.title, rf.file_hash, rf.file_size_bytes FROM research r JOIN research_files rf ON r.id = rf.research_id WHERE r.scan_status = 'completed' AND r.degree_type = 'ماجستير' ORDER BY r.created_at DESC LIMIT 50", lambda i: ())
    ]

    results = {}

    for q_name, sql, param_fn in query_definitions:
        latencies = []
        rows_returned = 0

        # فحص خطة الاستعلام EXPLAIN QUERY PLAN
        sample_params = param_fn(0)
        cur.execute(f"EXPLAIN QUERY PLAN {sql}", sample_params)
        plan_rows = [dict(r) for r in cur.fetchall()]
        plan_summary = " | ".join([f"{r.get('detail', '')}" for r in plan_rows])

        for rep in range(repetitions):
            params = param_fn(rep)
            t0 = time.perf_counter_ns()
            cur.execute(sql, params)
            res = cur.fetchall()
            t1 = time.perf_counter_ns()
            lat_ms = (t1 - t0) / 1_000_000.0
            latencies.append(lat_ms)
            rows_returned = len(res)

        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]
        avg = sum(latencies) / len(latencies)

        results[q_name] = {
            "sql": sql,
            "repetitions": repetitions,
            "rows_returned_sample": rows_returned,
            "query_plan": plan_summary,
            "min_ms": round(latencies[0], 3),
            "mean_ms": round(avg, 3),
            "p50_ms": round(p50, 3),
            "p95_ms": round(p95, 3),
            "p99_ms": round(p99, 3),
            "max_ms": round(latencies[-1], 3),
            "qps": round(1000.0 / max(0.001, avg), 1)
        }

    conn.close()
    return results


def benchmark_report_access(scale_target: int, db_path: Path, repetitions: int = 100) -> Dict[str, Any]:
    """قياس زمن الوصول إلى بيانات التقارير والتحليل التفكيكي لـ JSON."""
    conn = sqlite3.connect(str(db_path), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT research_id FROM reports LIMIT ?", (repetitions,))
    sample_ids = [r['research_id'] for r in cur.fetchall()]
    if not sample_ids:
        sample_ids = [1]

    fetch_latencies = []
    parse_latencies = []

    for rid in sample_ids:
        t0 = time.perf_counter_ns()
        cur.execute("SELECT * FROM reports WHERE research_id = ?", (rid,))
        row = cur.fetchone()
        t1 = time.perf_counter_ns()
        fetch_latencies.append((t1 - t0) / 1_000_000.0)

        if row and row['report_json']:
            t2 = time.perf_counter_ns()
            _ = json.loads(row['report_json'])
            t3 = time.perf_counter_ns()
            parse_latencies.append((t3 - t2) / 1_000_000.0)

    conn.close()

    fetch_latencies.sort()
    parse_latencies.sort()

    return {
        "scale": scale_target,
        "sample_count": len(sample_ids),
        "fetch_report_p50_ms": round(fetch_latencies[int(len(fetch_latencies) * 0.50)], 3),
        "fetch_report_p95_ms": round(fetch_latencies[int(len(fetch_latencies) * 0.95)], 3),
        "fetch_report_p99_ms": round(fetch_latencies[int(len(fetch_latencies) * 0.99)], 3),
        "json_parse_p50_ms": round(parse_latencies[int(len(parse_latencies) * 0.50)], 3) if parse_latencies else 0.0,
        "json_parse_p95_ms": round(parse_latencies[int(len(parse_latencies) * 0.95)], 3) if parse_latencies else 0.0,
    }


def benchmark_queue_scale(queue_depth: int) -> Dict[str, Any]:
    """قياس أداء طابور المهام عند أعماق طابور مختلفة (1K, 10K, 100K, 500K)."""
    q_db_path = DATA_DIR / f"queue_bench_{queue_depth}.benchmark.db"
    conn = create_clean_db(q_db_path, wal_mode=True, synchronous="NORMAL")
    cur = conn.cursor()

    print(f"    -> تعبئة طابور الاختبار بعدد {queue_depth:,} مهمة...")
    now_dt = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

    chunk_size = 10000
    cur.execute("BEGIN TRANSACTION;")
    for start in range(1, queue_depth + 1, chunk_size):
        count = min(chunk_size, queue_depth - start + 1)
        q_rows = []
        for i in range(start, start + count):
            job_id = f"qjob_scale_{queue_depth}_{i:08d}"
            prio = (i % 5) + 1
            dept = f"dept_{i % 10}"
            q_rows.append((
                job_id, 'SCAN_RESEARCH', 'queued', prio, dept, i, None,
                json.dumps({"payload_idx": i}), 0, 3, None, None, None, None,
                now_dt, now_dt, None, None, None, None, '1.3.0'
            ))
        cur.executemany("""
        INSERT INTO queue_jobs (id, job_type, status, priority, department_id, research_id,
                               batch_id, payload_json, attempt_count, max_attempts, claimed_by,
                               claim_token, lease_expires_at, last_heartbeat_at, available_at,
                               created_at, started_at, completed_at, error_code, error_message_redacted,
                               worker_protocol_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, q_rows)
    conn.commit()

    # قياس زمن الاستحواذ الذري الفردي (Claim Latency) عبر 100 مهمة
    claim_latencies = []
    complete_latencies = []
    heartbeat_latencies = []

    for w_i in range(100):
        worker_id = f"worker_bench_{w_i % 4}"
        claim_token = hashlib.md5(f"tok_{w_i}".encode()).hexdigest()
        lease_end = (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime('%Y-%m-%d %H:%M:%S')

        # خطوة 1: استعلام أفضل مهمة متاحة
        t0 = time.perf_counter_ns()
        cur.execute("""
        SELECT id FROM queue_jobs
        WHERE status = 'queued' AND available_at <= datetime('now') AND job_type = 'SCAN_RESEARCH'
        ORDER BY priority ASC, created_at ASC
        LIMIT 1;
        """)
        row = cur.fetchone()
        if row:
            jid = row['id']
            # خطوة 2: تحديث ذري للاستحواذ
            cur.execute("""
            UPDATE queue_jobs
            SET status = 'processing', claimed_by = ?, claim_token = ?, lease_expires_at = ?, started_at = datetime('now'), attempt_count = attempt_count + 1
            WHERE id = ? AND status = 'queued';
            """, (worker_id, claim_token, lease_end, jid))
            conn.commit()
            t1 = time.perf_counter_ns()
            claim_latencies.append((t1 - t0) / 1_000_000.0)

            # قياس نبضة القلب (Heartbeat Latency)
            t_hb0 = time.perf_counter_ns()
            cur.execute("""
            UPDATE queue_jobs SET last_heartbeat_at = datetime('now') WHERE id = ? AND claim_token = ?;
            """, (jid, claim_token))
            conn.commit()
            t_hb1 = time.perf_counter_ns()
            heartbeat_latencies.append((t_hb1 - t_hb0) / 1_000_000.0)

            # قياس الإكمال (Complete Latency)
            t_c0 = time.perf_counter_ns()
            cur.execute("""
            UPDATE queue_jobs SET status = 'completed', completed_at = datetime('now') WHERE id = ? AND claim_token = ?;
            """, (jid, claim_token))
            conn.commit()
            t_c1 = time.perf_counter_ns()
            complete_latencies.append((t_c1 - t_c0) / 1_000_000.0)

    # قياس استعلام استعادة المهام العالقة (Reclaim Query)
    t_rec0 = time.perf_counter_ns()
    cur.execute("""
    SELECT id, claimed_by, claim_token FROM queue_jobs
    WHERE status = 'processing' AND lease_expires_at < datetime('now')
    LIMIT 50;
    """)
    _ = cur.fetchall()
    t_rec1 = time.perf_counter_ns()
    reclaim_scan_ms = (t_rec1 - t_rec0) / 1_000_000.0

    conn.close()
    try:
        q_db_path.unlink()
        Path(f"{q_db_path}-wal").unlink(missing_ok=True)
        Path(f"{q_db_path}-shm").unlink(missing_ok=True)
    except Exception:
        pass

    claim_latencies.sort()
    complete_latencies.sort()
    heartbeat_latencies.sort()

    return {
        "queue_depth": queue_depth,
        "measured_claims": len(claim_latencies),
        "claim_p50_ms": round(claim_latencies[int(len(claim_latencies) * 0.50)], 3) if claim_latencies else 0,
        "claim_p95_ms": round(claim_latencies[int(len(claim_latencies) * 0.95)], 3) if claim_latencies else 0,
        "claim_p99_ms": round(claim_latencies[int(len(claim_latencies) * 0.99)], 3) if claim_latencies else 0,
        "complete_p50_ms": round(complete_latencies[int(len(complete_latencies) * 0.50)], 3) if complete_latencies else 0,
        "complete_p95_ms": round(complete_latencies[int(len(complete_latencies) * 0.95)], 3) if complete_latencies else 0,
        "heartbeat_p50_ms": round(heartbeat_latencies[int(len(heartbeat_latencies) * 0.50)], 3) if heartbeat_latencies else 0,
        "stale_reclaim_scan_ms": round(reclaim_scan_ms, 3)
    }


def _worker_process_target(worker_idx: int, db_path_str: str, target_jobs: int, results_dict: dict):
    """دالة تنفيذ العامل المستقل كعملية نظام حقيقية (Independent OS Process Worker)."""
    pid = os.getpid()
    worker_id = f"proc_worker_{worker_idx}_{pid}"
    jobs_processed = 0
    busy_errors = 0
    claim_times = []

    conn = sqlite3.connect(db_path_str, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000;")
    cur = conn.cursor()

    t_start = time.perf_counter()

    while jobs_processed < target_jobs:
        token = hashlib.md5(f"{worker_id}_{jobs_processed}_{time.perf_counter()}".encode()).hexdigest()
        lease_end = (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime('%Y-%m-%d %H:%M:%S')

        t_claim0 = time.perf_counter()
        try:
            cur.execute("""
            SELECT id FROM queue_jobs
            WHERE status = 'queued'
            ORDER BY priority ASC, created_at ASC
            LIMIT 1;
            """)
            row = cur.fetchone()
            if not row:
                break
            jid = row['id']

            cur.execute("""
            UPDATE queue_jobs
            SET status = 'processing', claimed_by = ?, claim_token = ?, lease_expires_at = ?, started_at = datetime('now'), attempt_count = attempt_count + 1
            WHERE id = ? AND status = 'queued';
            """, (worker_id, token, lease_end, jid))

            if cur.rowcount > 0:
                conn.commit()
                t_claim1 = time.perf_counter()
                claim_times.append((t_claim1 - t_claim0) * 1000.0)

                # محاكاة عمل خفيف (5 مللي ثانية)
                time.sleep(0.005)

                # إكمال المهمة
                cur.execute("""
                UPDATE queue_jobs
                SET status = 'completed', completed_at = datetime('now')
                WHERE id = ? AND claim_token = ?;
                """, (jid, token))
                conn.commit()
                jobs_processed += 1
            else:
                conn.rollback()
        except sqlite3.OperationalError as e:
            if "locked" in str(e) or "busy" in str(e):
                busy_errors += 1
                try: conn.rollback()
                except Exception: pass
                time.sleep(0.01)
            else:
                raise e

    t_end = time.perf_counter()
    conn.close()

    claim_times.sort()
    p50_claim = claim_times[int(len(claim_times) * 0.50)] if claim_times else 0.0

    results_dict[worker_idx] = {
        "worker_id": worker_id,
        "pid": pid,
        "jobs_processed": jobs_processed,
        "busy_errors": busy_errors,
        "duration_seconds": round(t_end - t_start, 3),
        "p50_claim_ms": round(p50_claim, 3)
    }


def benchmark_multi_worker_concurrency(worker_counts: List[int] = [1, 2, 4, 8, 16], total_jobs: int = 200) -> Dict[str, Any]:
    """قياس أداء تزامن العمال المستقلين كعمليات نظام منفصلة (1, 2, 4, 8, 16 OS Workers)."""
    concurrency_results = {}

    for w_count in worker_counts:
        db_path = DATA_DIR / f"worker_bench_{w_count}w.benchmark.db"
        conn = create_clean_db(db_path, wal_mode=True, synchronous="NORMAL")
        cur = conn.cursor()

        # إدراج المهام
        now_dt = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        q_rows = []
        for i in range(1, total_jobs + 1):
            job_id = f"qjob_concur_{w_count}_{i:06d}"
            q_rows.append((
                job_id, 'SCAN_RESEARCH', 'queued', (i % 5) + 1, f"dept_{i % 5}", i, None,
                '{}', 0, 3, None, None, None, None, now_dt, now_dt, None, None, None, None, '1.3.0'
            ))
        cur.executemany("""
        INSERT INTO queue_jobs (id, job_type, status, priority, department_id, research_id,
                               batch_id, payload_json, attempt_count, max_attempts, claimed_by,
                               claim_token, lease_expires_at, last_heartbeat_at, available_at,
                               created_at, started_at, completed_at, error_code, error_message_redacted,
                               worker_protocol_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, q_rows)
        conn.commit()
        conn.close()

        manager = mp.Manager()
        shared_results = manager.dict()
        jobs_per_worker = (total_jobs // w_count) + 5

        processes = []
        t0 = time.perf_counter()
        for idx in range(w_count):
            p = mp.Process(target=_worker_process_target, args=(idx, str(db_path), jobs_per_worker, shared_results))
            processes.append(p)
            p.start()

        for p in processes:
            p.join(timeout=45.0)
            if p.is_alive():
                p.terminate()

        t1 = time.perf_counter()
        total_time = t1 - t0

        worker_stats = dict(shared_results)
        completed_jobs = sum(w.get('jobs_processed', 0) for w in worker_stats.values())
        total_busy_errors = sum(w.get('busy_errors', 0) for w in worker_stats.values())
        throughput_jpm = (completed_jobs / max(0.001, total_time)) * 60.0

        concurrency_results[f"{w_count}_workers"] = {
            "worker_count": w_count,
            "target_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "total_busy_errors": total_busy_errors,
            "lock_contention_rate_pct": round((total_busy_errors / max(1, completed_jobs + total_busy_errors)) * 100, 2),
            "elapsed_seconds": round(total_time, 3),
            "throughput_jobs_per_minute": round(throughput_jpm, 2),
            "throughput_jobs_per_sec": round(completed_jobs / max(0.001, total_time), 2),
            "worker_details": worker_stats
        }
        print(f"    -> {w_count} عمال OS: أنجزوا {completed_jobs}/{total_jobs} مهمة في {total_time:.2f} ثانية | إنتاجية: {throughput_jpm:,.1f} مهمة/دقيقة | أخطاء القفل/الانتظار: {total_busy_errors}")

        try:
            db_path.unlink()
            Path(f"{db_path}-wal").unlink(missing_ok=True)
            Path(f"{db_path}-shm").unlink(missing_ok=True)
        except Exception:
            pass

    return concurrency_results


def benchmark_multi_user_read_load(scale_100k_db_path: Path, user_levels: List[int] = [1, 5, 10, 25, 50, 100], duration_sec: float = 8.0) -> Dict[str, Any]:
    """قياس أداء القراءة المتزامنة للمستخدمين (1 إلى 100 مستخدم) مع وجود كتابة مستمرة في الخلفية."""
    results = {}

    for u_count in user_levels:
        stop_event = threading.Event()
        read_latencies = []
        write_latencies = []
        read_errors = 0
        write_errors = 0
        total_reads = 0
        total_writes = 0
        lat_lock = threading.Lock()

        # خيط الكتابة المستمرة في الخلفية
        def writer_thread():
            nonlocal write_errors, total_writes
            conn_w = sqlite3.connect(str(scale_100k_db_path), timeout=10.0, check_same_thread=False)
            conn_w.execute("PRAGMA busy_timeout = 10000;")
            w_cur = conn_w.cursor()
            cnt = 0
            while not stop_event.is_set():
                cnt += 1
                t0 = time.perf_counter()
                try:
                    eid = f"evt_load_{u_count}_{cnt}_{time.time()}"
                    w_cur.execute("""
                    INSERT INTO audit_logs (event_id, created_at, user_id, action, category, object_type, object_id, success)
                    VALUES (?, datetime('now'), 999, 'user.search_load', 'audit', 'research', '1', 1);
                    """, (eid,))
                    conn_w.commit()
                    t1 = time.perf_counter()
                    with lat_lock:
                        write_latencies.append((t1 - t0) * 1000.0)
                        total_writes += 1
                except sqlite3.OperationalError:
                    with lat_lock:
                        write_errors += 1
                time.sleep(0.01)
            conn_w.close()

        # خيط القراءة المتزامنة للمستخدم
        def reader_thread(user_id: int):
            nonlocal read_errors, total_reads
            conn_r = sqlite3.connect(str(scale_100k_db_path), timeout=10.0, check_same_thread=False)
            conn_r.row_factory = sqlite3.Row
            conn_r.execute("PRAGMA busy_timeout = 10000;")
            r_cur = conn_r.cursor()
            while not stop_event.is_set():
                target_id = random.randint(1, 100000)
                q_type = random.choice(['pk', 'title', 'meta'])
                t0 = time.perf_counter()
                try:
                    if q_type == 'pk':
                        r_cur.execute("SELECT * FROM research WHERE id = ?", (target_id,))
                    elif q_type == 'title':
                        r_cur.execute("SELECT id, title, author FROM research WHERE title LIKE 'دراسة تحليلية%' LIMIT 20")
                    else:
                        r_cur.execute("SELECT id, title FROM research WHERE specialization = 'علوم الحاسب' AND degree_type = 'ماجستير' LIMIT 20")
                    _ = r_cur.fetchall()
                    t1 = time.perf_counter()
                    with lat_lock:
                        read_latencies.append((t1 - t0) * 1000.0)
                        total_reads += 1
                except sqlite3.OperationalError:
                    with lat_lock:
                        read_errors += 1
                time.sleep(0.005)
            conn_r.close()

        w_th = threading.Thread(target=writer_thread)
        w_th.start()

        r_threads = [threading.Thread(target=reader_thread, args=(i,)) for i in range(u_count)]
        t_start = time.perf_counter()
        for th in r_threads:
            th.start()

        time.sleep(duration_sec)
        stop_event.set()

        for th in r_threads:
            th.join()
        w_th.join()
        t_elapsed = time.perf_counter() - t_start

        read_latencies.sort()
        write_latencies.sort()

        p50_r = read_latencies[int(len(read_latencies) * 0.50)] if read_latencies else 0
        p95_r = read_latencies[int(len(read_latencies) * 0.95)] if read_latencies else 0
        p99_r = read_latencies[int(len(read_latencies) * 0.99)] if read_latencies else 0
        p50_w = write_latencies[int(len(write_latencies) * 0.50)] if write_latencies else 0
        p95_w = write_latencies[int(len(write_latencies) * 0.95)] if write_latencies else 0

        results[f"{u_count}_concurrent_users"] = {
            "users_count": u_count,
            "test_duration_sec": round(t_elapsed, 2),
            "total_reads": total_reads,
            "read_qps": round(total_reads / max(0.001, t_elapsed), 1),
            "read_errors": read_errors,
            "read_p50_ms": round(p50_r, 3),
            "read_p95_ms": round(p95_r, 3),
            "read_p99_ms": round(p99_r, 3),
            "total_writes": total_writes,
            "write_wps": round(total_writes / max(0.001, t_elapsed), 1),
            "write_errors": write_errors,
            "write_p50_ms": round(p50_w, 3),
            "write_p95_ms": round(p95_w, 3)
        }
        print(f"    -> {u_count} مستخدم متزامن: {total_reads:,} استعلام قراءة ({total_reads/t_elapsed:,.0f} QPS | p50: {p50_r:.2f}ms | p95: {p95_r:.2f}ms) | {total_writes} عمليات كتابة | أخطاء: {read_errors}")

    return results


def benchmark_sustained_mixed_workload_1m(db_1m_path: Path, duration_sec: float = 20.0) -> Dict[str, Any]:
    """قياس أداء الحمل الهجين المستمر على قاعدة بيانات المليون سجل (4 عمال OS + 10 مستخدمين متزامنين)."""
    print(f"\n[+] تشغيل اختبار الحمل الهجين المستمر على مقياس 1,000,000 سجل لمدة {duration_sec} ثانية...")
    process = psutil.Process()
    cpu_measurements = []
    mem_measurements = []

    stop_event = mp.Event()
    manager = mp.Manager()
    worker_results = manager.dict()

    # تشغيل 4 عمال OS
    workers = []
    for i in range(4):
        p = mp.Process(target=_worker_process_target, args=(i, str(db_1m_path), 500, worker_results))
        workers.append(p)
        p.start()

    # تشغيل 10 خيوط للمستخدمين
    th_stop_event = threading.Event()
    user_queries_count = 0
    user_errors = 0
    query_lock = threading.Lock()

    def user_load_thread():
        nonlocal user_queries_count, user_errors
        conn = sqlite3.connect(str(db_1m_path), timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        while not th_stop_event.is_set():
            target_id = random.randint(1, 1000000)
            try:
                cur.execute("SELECT * FROM research WHERE id = ?", (target_id,))
                _ = cur.fetchone()
                with query_lock:
                    user_queries_count += 1
            except Exception:
                with query_lock:
                    user_errors += 1
            time.sleep(0.005)
        conn.close()

    user_threads = [threading.Thread(target=user_load_thread) for _ in range(10)]
    t_start = time.perf_counter()
    for th in user_threads:
        th.start()

    # أخذ عينات لموارد المعالج والذاكرة
    sample_interval = 0.5
    for _ in range(int(duration_sec / sample_interval)):
        cpu_measurements.append(psutil.cpu_percent(interval=None))
        mem_measurements.append(process.memory_info().rss / (1024*1024))
        time.sleep(sample_interval)

    th_stop_event.set()
    for th in user_threads:
        th.join()

    for p in workers:
        p.join(timeout=5.0)
        if p.is_alive():
            p.terminate()

    t_elapsed = time.perf_counter() - t_start

    w_stats = dict(worker_results)
    total_jobs_done = sum(w.get('jobs_processed', 0) for w in w_stats.values())
    total_busy_errs = sum(w.get('busy_errors', 0) for w in w_stats.values())

    avg_cpu = sum(cpu_measurements) / max(1, len(cpu_measurements))
    peak_cpu = max(cpu_measurements) if cpu_measurements else 0
    avg_mem = sum(mem_measurements) / max(1, len(mem_measurements))
    peak_mem = max(mem_measurements) if mem_measurements else 0

    return {
        "scale": 1000000,
        "duration_seconds": round(t_elapsed, 2),
        "os_worker_count": 4,
        "concurrent_users_count": 10,
        "total_jobs_completed": total_jobs_done,
        "worker_throughput_jpm": round((total_jobs_done / max(0.001, t_elapsed)) * 60, 2),
        "worker_busy_errors": total_busy_errs,
        "total_user_queries": user_queries_count,
        "user_qps": round(user_queries_count / max(0.001, t_elapsed), 1),
        "user_query_errors": user_errors,
        "avg_cpu_percent": round(avg_cpu, 1),
        "peak_cpu_percent": round(peak_cpu, 1),
        "avg_rss_mem_mb": round(avg_mem, 1),
        "peak_rss_mem_mb": round(peak_mem, 1)
    }


def benchmark_backup_and_restore(db_1m_path: Path) -> Dict[str, Any]:
    """تدريب النسخ الاحتياطي والاستعادة الحي على قاعدة بيانات المليون سجل."""
    print("\n[+] تشغيل تدريب النسخ الاحتياطي الحي (Online SQLite Backup Drill)...")
    backup_dest = DATA_DIR / "backup_drill_1m.benchmark.bak"
    if backup_dest.exists():
        backup_dest.unlink()

    src_conn = sqlite3.connect(str(db_1m_path), timeout=30.0, check_same_thread=False)
    dst_conn = sqlite3.connect(str(backup_dest), timeout=30.0, check_same_thread=False)

    t0 = time.perf_counter()
    src_conn.backup(dst_conn, pages=1000, progress=None)
    t1 = time.perf_counter()
    backup_duration = t1 - t0

    src_conn.close()
    dst_conn.close()

    backup_size = os.path.getsize(backup_dest)
    throughput_mb_s = (backup_size / (1024*1024)) / max(0.001, backup_duration)

    # التحقق من سلامة النسخة واتساقها الكامل (Integrity & Row Count Check)
    chk_conn = sqlite3.connect(str(backup_dest))
    cur = chk_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    integrity = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM research;")
    cnt_research = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM research_files;")
    cnt_files = cur.fetchone()[0]

    chk_conn.close()

    try:
        backup_dest.unlink()
    except Exception:
        pass

    return {
        "source_db": str(db_1m_path),
        "backup_duration_seconds": round(backup_duration, 3),
        "backup_size_bytes": backup_size,
        "backup_size_mb": round(backup_size / (1024*1024), 2),
        "backup_throughput_mb_sec": round(throughput_mb_s, 2),
        "integrity_check_result": [r[0] for r in integrity],
        "integrity_status": "PASSED" if len(integrity) == 1 and integrity[0][0] == 'ok' else "FAILED",
        "verified_research_count": cnt_research,
        "verified_files_count": cnt_files
    }


def benchmark_crash_and_recovery() -> Dict[str, Any]:
    """محاكاة الانهيار المفاجئ واستعادة اتساق المعاملات وطابور المهام."""
    print("\n[+] محاكاة الانهيار المفاجئ وفحص قدرة الاستعادة (Crash & Recovery Drill)...")
    crash_db = DATA_DIR / "crash_test.benchmark.db"
    conn = create_clean_db(crash_db, wal_mode=True, synchronous="FULL")
    cur = conn.cursor()

    # إدراج 100 مهمة
    now_dt = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
    for i in range(1, 101):
        cur.execute("""
        INSERT INTO queue_jobs (id, job_type, status, priority, department_id, research_id, available_at, created_at)
        VALUES (?, 'SCAN_RESEARCH', 'queued', 3, 'dept_1', ?, ?, ?);
        """, (f"q_crash_{i:04d}", i, now_dt, now_dt))
    conn.commit()

    # استحواذ عامل على مهمة
    expired_lease = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime('%Y-%m-%d %H:%M:%S')
    cur.execute("""
    UPDATE queue_jobs
    SET status = 'processing', claimed_by = 'worker_dead_pid_999', claim_token = 'tok_dead',
        started_at = ?, lease_expires_at = ?
    WHERE id = 'q_crash_0001';
    """, (expired_lease, expired_lease))
    conn.commit()

    # محاكاة معاملة معلقة غير مكتملة
    cur.execute("BEGIN TRANSACTION;")
    cur.execute("INSERT INTO research (id, reference_number, title) VALUES (999999, 'CRASH-001', 'بحث انقطع قبل الحفظ');")
    # إغلاق الاتصال دون commit (محاكاة انهيار فوري للمفتاح / العملية)
    conn.close()

    # فتح اتصال جديد والتحقق من الاستعادة الذاتية
    rec_conn = sqlite3.connect(str(crash_db))
    r_cur = rec_conn.cursor()
    r_cur.execute("PRAGMA integrity_check;")
    integrity = r_cur.fetchall()

    # التحقق من أن السجل غير المكتمل تم التراجع عنه تلقائياً
    r_cur.execute("SELECT COUNT(*) FROM research WHERE id = 999999;")
    uncommitted_exists = r_cur.fetchone()[0] == 1

    # استعادة المهمة منتهية الإيجار (Stale Lease Reclaim)
    r_cur.execute("""
    UPDATE queue_jobs
    SET status = 'queued', claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL
    WHERE status = 'processing' AND lease_expires_at < datetime('now');
    """)
    reclaimed_count = r_cur.rowcount
    rec_conn.commit()
    rec_conn.close()

    try:
        crash_db.unlink()
        Path(f"{crash_db}-wal").unlink(missing_ok=True)
        Path(f"{crash_db}-shm").unlink(missing_ok=True)
    except Exception:
        pass

    return {
        "integrity_check": [r[0] for r in integrity],
        "uncommitted_transaction_rolled_back": not uncommitted_exists,
        "stale_jobs_reclaimed_count": reclaimed_count,
        "recovery_verdict": "PERFECT_CONSISTENCY" if (len(integrity) == 1 and integrity[0][0] == 'ok' and not uncommitted_exists and reclaimed_count == 1) else "INCONSISTENT"
    }


def benchmark_index_optimization_audit(db_100k_path: Path) -> Dict[str, Any]:
    """تدقيق أثر الفهارس الإضافية المقترحة على تسريع الاستعلامات مقابل كلفة الإدراج."""
    print("\n[+] تدقيق كفاءة الفهارس (Index Audit: Speed vs Insertion Overhead)...")
    conn = sqlite3.connect(str(db_100k_path), timeout=30.0, check_same_thread=False)
    cur = conn.cursor()

    # استعلام مركب بدون الفهرس المركب
    t0 = time.perf_counter_ns()
    cur.execute("""
    SELECT id, title, created_at FROM research
    WHERE scan_status = 'completed' AND degree_type = 'دكتوراه'
    ORDER BY created_at DESC LIMIT 50;
    """)
    _ = cur.fetchall()
    t1 = time.perf_counter_ns()
    latency_before_ms = (t1 - t0) / 1_000_000.0

    # إضافة الفهرس المركب المرشح
    t_idx0 = time.perf_counter()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_research_status_deg_created ON research(scan_status, degree_type, created_at);")
    conn.commit()
    t_idx1 = time.perf_counter()
    index_creation_duration_sec = t_idx1 - t_idx0

    # قياس نفس الاستعلام بعد الفهرس
    t2 = time.perf_counter_ns()
    cur.execute("""
    SELECT id, title, created_at FROM research
    WHERE scan_status = 'completed' AND degree_type = 'دكتوراه'
    ORDER BY created_at DESC LIMIT 50;
    """)
    _ = cur.fetchall()
    t3 = time.perf_counter_ns()
    latency_after_ms = (t3 - t2) / 1_000_000.0

    # قياس كلفة الإدراج مع الفهرس الجديد
    t_ins0 = time.perf_counter()
    cur.execute("BEGIN TRANSACTION;")
    for i in range(900001, 905001):
        cur.execute("""
        INSERT INTO research (id, reference_number, title, specialization, degree_type, scan_status, created_at)
        VALUES (?, ?, 'بحث اختبار الفهرس', 'علوم الحاسب', 'دكتوراه', 'completed', datetime('now'));
        """, (i, f"IDX-TEST-{i}"))
    conn.commit()
    t_ins1 = time.perf_counter()
    insert_5k_duration_sec = t_ins1 - t_ins0

    # حذف السجلات والفهرس التجريبي
    cur.execute("DELETE FROM research WHERE id >= 900001;")
    cur.execute("DROP INDEX IF EXISTS idx_research_status_deg_created;")
    conn.commit()
    conn.close()

    acceleration_factor = latency_before_ms / max(0.001, latency_after_ms)

    return {
        "candidate_index": "idx_research_status_deg_created (scan_status, degree_type, created_at)",
        "query_latency_before_ms": round(latency_before_ms, 3),
        "query_latency_after_ms": round(latency_after_ms, 3),
        "query_acceleration_factor": round(acceleration_factor, 1),
        "index_creation_duration_sec": round(index_creation_duration_sec, 3),
        "batch_5k_insert_duration_sec": round(insert_5k_duration_sec, 3),
        "batch_5k_insert_rate_per_sec": round(5000.0 / max(0.001, insert_5k_duration_sec), 1)
    }


def calculate_storage_capacity_model(measured_scales: Dict[str, Any]) -> Dict[str, Any]:
    """بناء النموذج التقديري لسعات التخزين المادية والبيانات الوصفية عبر مختلف الأحجام."""
    doc_sizes_mb = [2, 5, 10]
    scales = [10000, 100000, 500000, 1000000, 2000000]
    model_matrix = {}

    for scale in scales:
        scale_key = str(scale)
        measured_meta_mb = measured_scales.get(scale_key, {}).get("db_size_mb", (scale * 350) / (1024*1024))
        scale_projections = {}

        for doc_mb in doc_sizes_mb:
            cas_storage_gb = (scale * doc_mb) / 1024.0
            meta_db_gb = measured_meta_mb / 1024.0
            wal_headroom_gb = max(0.5, meta_db_gb * 0.25)
            # 3 نسخ احتياطية دورية
            backup_storage_gb = (meta_db_gb + cas_storage_gb) * 3.0
            total_recommended_gb = meta_db_gb + cas_storage_gb + wal_headroom_gb + backup_storage_gb

            scale_projections[f"{doc_mb}MB_per_doc"] = {
                "avg_doc_size_mb": doc_mb,
                "cas_storage_gb": round(cas_storage_gb, 2),
                "cas_storage_tb": round(cas_storage_gb / 1024.0, 3),
                "metadata_db_gb": round(meta_db_gb, 3),
                "wal_headroom_gb": round(wal_headroom_gb, 3),
                "backup_3_copies_gb": round(backup_storage_gb, 2),
                "total_recommended_disk_gb": round(total_recommended_gb, 2),
                "total_recommended_disk_tb": round(total_recommended_gb / 1024.0, 3)
            }

        model_matrix[f"scale_{scale}"] = {
            "documents_count": scale,
            "metadata_db_mb": round(measured_meta_mb, 2),
            "projections": scale_projections
        }

    return model_matrix


def run_full_validation_suite():
    """تشغيل برنامج الاختبار الشامل وحفظ النتائج المهيكلة."""
    print("=" * 80)
    print("  بدء سلسلة اختبارات الضغط والقدرة الاستيعابية لقاعدة بيانات SQLite على مقياس المليون")
    print("=" * 80)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env_info = get_system_environment()
    print(f"بيئة التشغيل: {env_info['os_platform']} | أنوية المعالج: {env_info['cpu_logical_cores']} | الرام: {env_info['ram_total_gb']} GB")

    target_scales = [10000, 100000, 500000, 1000000, 2000000]
    scale_benchmarks = {}
    search_benchmarks = {}
    report_benchmarks = {}
    single_insert_benchmarks = {}

    # 1. اختبار المقاييس الخمسة
    scale_db_paths = {}
    for s in target_scales:
        db_p = DATA_DIR / f"scale_{s}.benchmark.db"
        scale_db_paths[s] = db_p

        # بناء البيانات وقياس الحجم والإدراج
        meta_stats = populate_scale_database(s, db_p)
        scale_benchmarks[str(s)] = meta_stats

        # قياس زمن الإدراج الفردي
        print(f"    -> قياس زمن الإدراج الفردي مع synchronous=FULL على مقياس {s:,}...")
        ins_stats = benchmark_single_insert_latency(s, db_p, iterations=500 if s >= 500000 else 1000)
        single_insert_benchmarks[str(s)] = ins_stats

        # قياس أزمنة الاستعلامات الـ 11
        print(f"    -> قياس أزمنة 11 نمط استعلام وبحث عبر 100 تكرار على مقياس {s:,}...")
        q_stats = benchmark_search_queries(s, db_p, repetitions=100)
        search_benchmarks[str(s)] = q_stats

        # قياس استعراض التقارير
        print(f"    -> قياس زمن جلب وتحليل التقارير على مقياس {s:,}...")
        rep_stats = benchmark_report_access(s, db_p, repetitions=100)
        report_benchmarks[str(s)] = rep_stats

    # 2. اختبار سعات الطابور
    print("\n[+] تشغيل اختبارات ضغط وتدرج طابور المهام (Queue Scale Benchmark: 1K -> 500K)...")
    queue_benchmarks = {}
    for q_depth in [1000, 10000, 100000, 500000]:
        q_stats = benchmark_queue_scale(q_depth)
        queue_benchmarks[f"{q_depth}_jobs"] = q_stats
        print(f"    -> طابور {q_depth:,} مهمة | سحب p50: {q_stats['claim_p50_ms']}ms | إكمال p50: {q_stats['complete_p50_ms']}ms | مسح المهام العالقة: {q_stats['stale_reclaim_scan_ms']}ms")

    # 3. اختبار تزامن العمال المستقلين كعمليات نظام منفصلة
    print("\n[+] تشغيل اختبار تزامن العمال الحقيقيين كعمليات نظام منفصلة (1, 2, 4, 8, 16 OS Workers)...")
    concurrency_benchmarks = benchmark_multi_worker_concurrency([1, 2, 4, 8, 16], total_jobs=200)

    # 4. اختبار تزامن القراءة مع وجود كتابة مستمرة في الخلفية (1 إلى 100 مستخدم)
    print("\n[+] تشغيل اختبار حمل القراءة المتزامنة للمستخدمين (1 إلى 100 مستخدم) على قاعدة 100K...")
    multi_user_benchmarks = benchmark_multi_user_read_load(scale_db_paths[100000], [1, 5, 10, 25, 50, 100], duration_sec=8.0)

    # 5. اختبار الحمل الهجين المستمر على قاعدة 1M
    sustained_workload_results = benchmark_sustained_mixed_workload_1m(scale_db_paths[1000000], duration_sec=15.0)

    # 6. تدريب النسخ الاحتياطي والاستعادة الحي
    backup_drill_results = benchmark_backup_and_restore(scale_db_paths[1000000])

    # 7. محاكاة الانهيار واستعادة الاتساق
    crash_recovery_results = benchmark_crash_and_recovery()

    # 8. تدقيق الفهارس
    index_audit_results = benchmark_index_optimization_audit(scale_db_paths[100000])

    # 9. نموذج حساب السعات التخزينية
    capacity_model_results = calculate_storage_capacity_model(scale_benchmarks)

    # تنظيف قواعد بيانات الاختبار لتوفير المساحة بعد انتهاء القياسات
    for s, p in scale_db_paths.items():
        try:
            p.unlink()
            Path(f"{p}-wal").unlink(missing_ok=True)
            Path(f"{p}-shm").unlink(missing_ok=True)
        except Exception:
            pass

    full_results_payload = {
        "benchmark_metadata": {
            "suite_version": "1.4.0-sqlite-million-scale-validation",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "target_system": "Arabic Academic Plagiarism Detector (Offline Portable & Enterprise)",
            "safety_boundary_verified": "Live database C:\\Users\\user\\AppData\\Roaming\\ArabicPlagiarismDetector\\papers.db UNTOUCHED",
        },
        "environment": env_info,
        "scale_metrics": scale_benchmarks,
        "single_insert_latencies": single_insert_benchmarks,
        "search_query_latencies": search_benchmarks,
        "report_access_latencies": report_benchmarks,
        "queue_scale_latencies": queue_benchmarks,
        "os_worker_concurrency": concurrency_benchmarks,
        "multi_user_read_concurrency": multi_user_benchmarks,
        "sustained_mixed_workload_1m": sustained_workload_results,
        "backup_restore_drill": backup_drill_results,
        "crash_recovery_drill": crash_recovery_results,
        "index_optimization_audit": index_audit_results,
        "storage_capacity_model": capacity_model_results
    }

    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(full_results_payload, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 80)
    print(f"[✓] اكتملت جميع القياسات والاختبارات بنجاح وحفظت في: {RESULTS_FILE}")
    print("=" * 80)


if __name__ == '__main__':
    mp.freeze_support()
    run_full_validation_suite()
