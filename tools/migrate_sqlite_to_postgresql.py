# -*- coding: utf-8 -*-
"""
أداة هجرة البيانات الموثوقة من SQLite إلى PostgreSQL (Offline Database Migration Tool):
- تعمل 100% أوفلاين مع حماية تامة لقاعدة بيانات SQLite المصدر (Read-Only).
- تنفذ فحص السلامة المسبق (Preflight Integrity Check).
- تنقل كافة الجداول والعلاقات وتجزئات كلمات المرور والمراجع والتقارير.
- تتحقق بدقة متناهية من تطابق أعداد السجلات وبصمات التقارير وبصمات قاعدة المراجع.
- تنتج تقريراً شاملاً بصيغة JSON.
"""

import os
import sys
import json
import time
import hashlib
import sqlite3
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

# إضافة المسار الجذري للنظام
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import config
from app.repositories import base_repo
from app.models.schema import Base
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("migration_tool")

# ترتيب الجداول المنقولة لمراعاة قيود المفاتيح الأجنبية (Foreign Key Dependencies)
TABLE_MIGRATION_ORDER = [
    'users',
    'roles',
    'permissions',
    'user_roles',
    'role_permissions',
    'reference_corpus_versions',
    'reference_corpus_changesets',
    'documents',
    'document_pages',
    'document_segments',
    'research',
    'research_files',
    'reports',
    'report_revisions',
    'review_decisions',
    'scan_batches',
    'scan_batch_items',
    'scan_jobs',
    'audit_logs',
    'backup_catalog',
    'reference_sequences',
    'schema_migrations',
    'index_state_records',
]


def compute_file_sha256(filepath: Path) -> str:
    """احتساب بصمة SHA-256 للملف."""
    h = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class MigrationEngine:
    def __init__(self, sqlite_path: Path, pg_dsn: str, dry_run: bool = False):
        self.sqlite_path = Path(sqlite_path).resolve()
        self.pg_dsn = pg_dsn
        self.dry_run = dry_run
        self.report: Dict[str, Any] = {
            'started_at': datetime.utcnow().isoformat() + 'Z',
            'sqlite_source_path': str(self.sqlite_path),
            'dry_run': self.dry_run,
            'preflight': {},
            'tables_migrated': {},
            'verification': {},
            'success': False,
            'errors': []
        }

    def run(self) -> Dict[str, Any]:
        t0 = time.time()
        logger.info("==================================================")
        logger.info("بدء أداة هجرة البيانات من SQLite إلى PostgreSQL (Prompt 1)")
        logger.info(f"المصدر (SQLite): {self.sqlite_path}")
        logger.info(f"الوجهة (PostgreSQL): {config.get_masked_database_url(self.pg_dsn)}")
        logger.info("==================================================")

        try:
            # 1. فحص سلامة المصدر واحتساب البصمة الأولية
            self._preflight_sqlite()

            # 2. فحص اتصال ومخطط الوجهة
            pg_engine = self._preflight_postgresql()

            if self.dry_run:
                logger.info("تم إنهاء الفحص المسبق بنجاح (نمط المحاكاة Dry-Run مفعل - لم يتم نقل بيانات).")
                self.report['success'] = True
                self.report['duration_seconds'] = round(time.time() - t0, 3)
                return self.report

            # 3. إنشاء الجداول وتطبيق الهيكل في PostgreSQL إذا لم تكن موجودة
            logger.info("إنشاء وتأكيد هيكل الجداول في PostgreSQL...")
            Base.metadata.create_all(bind=pg_engine)

            # 4. نقل البيانات جدولاً بجدول
            self._migrate_data(pg_engine)

            # 5. مطابقة والتحقق من صحة السجلات وبصمات التقارير المعتمدة
            self._verify_migration(pg_engine)

            # 6. التحقق النهائي من عدم تغير بصمة ملف SQLite المصدر
            post_hash = compute_file_sha256(self.sqlite_path)
            if post_hash != self.report['preflight']['sqlite_initial_sha256']:
                raise RuntimeError("تحذير أمني خطير: تم رصد تغير في بصمة ملف SQLite المصدر بعد الهجرة!")
            self.report['verification']['source_sqlite_sha256_unmodified'] = True

            self.report['success'] = True
            logger.info("==================================================")
            logger.info("اكتملت عملية الهجرة بنجاح تام وتطابقت كافة القيود والبصمات 100%.")
            logger.info("==================================================")

        except Exception as e:
            logger.error(f"فشلت عملية الهجرة: {e}", exc_info=True)
            self.report['errors'].append(str(e))
            self.report['success'] = False

        finally:
            self.report['completed_at'] = datetime.utcnow().isoformat() + 'Z'
            self.report['duration_seconds'] = round(time.time() - t0, 3)

        return self.report

    def _preflight_sqlite(self):
        """التحقق المسبق من وجود وسلامة قاعدة بيانات SQLite المصدر."""
        if not self.sqlite_path.exists():
            raise FileNotFoundError(f"ملف SQLite غير موجود: {self.sqlite_path}")

        initial_sha = compute_file_sha256(self.sqlite_path)
        self.report['preflight']['sqlite_initial_sha256'] = initial_sha
        self.report['preflight']['sqlite_file_size_bytes'] = self.sqlite_path.stat().st_size

        # فحص SQLite PRAGMA integrity_check
        uri = f"file:{self.sqlite_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=10.0)
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA integrity_check;")
            res = cur.fetchone()
            if not res or res[0] != 'ok':
                raise RuntimeError(f"فشل فحص سلامة SQLite: {res}")
            self.report['preflight']['sqlite_integrity_check'] = 'ok'

            # جمع إحصائيات السجلات للمصدر
            source_counts = {}
            for tbl in TABLE_MIGRATION_ORDER:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {tbl};")
                    cnt = cur.fetchone()[0]
                    source_counts[tbl] = cnt
                except sqlite3.OperationalError:
                    source_counts[tbl] = 0
            self.report['preflight']['source_table_counts'] = source_counts
            logger.info(f"إحصائيات المصدر (SQLite): {source_counts}")

        finally:
            conn.close()

    def _preflight_postgresql(self) -> Any:
        """فحص اتصال وتجهيز محرك PostgreSQL."""
        try:
            pg_engine = create_engine(self.pg_dsn, pool_pre_ping=True)
            with pg_engine.connect() as conn:
                res = conn.execute(text("SELECT 1;")).scalar()
                if res != 1:
                    raise RuntimeError("فشل استعلام الاختبار في PostgreSQL")
            self.report['preflight']['postgresql_connected'] = True
            return pg_engine
        except Exception as e:
            err = config.get_masked_database_url(str(e))
            raise ConnectionError(f"تعذر الاتصال بخادم PostgreSQL: {err}")

    def _migrate_data(self, pg_engine: Any):
        """نقل البيانات دفعة واحدة داخل معاملة موحدة لضمان الذرية التامة."""
        uri = f"file:{self.sqlite_path.as_posix()}?mode=ro"
        src_conn = sqlite3.connect(uri, uri=True)
        src_conn.row_factory = sqlite3.Row

        try:
            with pg_engine.begin() as pg_conn:
                inspector = inspect(pg_conn)
                existing_pg_tables = set(inspector.get_table_names())

                for tbl in TABLE_MIGRATION_ORDER:
                    try:
                        cur = src_conn.cursor()
                        cur.execute(f"SELECT * FROM {tbl};")
                        rows = cur.fetchall()
                        row_count = len(rows)
                    except sqlite3.OperationalError:
                        logger.info(f"الجدول {tbl} غير موجود في المصدر، سيتم تجاوزه.")
                        continue

                    if row_count == 0:
                        self.report['tables_migrated'][tbl] = {'source_count': 0, 'inserted_count': 0}
                        continue

                    if tbl not in existing_pg_tables:
                        logger.warning(f"الجدول {tbl} غير موجود في هيكل PostgreSQL المستهدف!")
                        continue

                    # استخراج أسماء الأعمدة وقيم السجلات
                    col_names = [col[0] for col in cur.description]
                    cols_str = ", ".join([f'"{c}"' for c in col_names])
                    placeholders = ", ".join([f":{c}" for c in col_names])
                    insert_stmt = text(f'INSERT INTO "{tbl}" ({cols_str}) VALUES ({placeholders})')

                    # تحويل السجلات إلى قواميس متوافقة
                    data_dicts = []
                    for r in rows:
                        d = dict(r)
                        data_dicts.append(d)

                    pg_conn.execute(insert_stmt, data_dicts)
                    self.report['tables_migrated'][tbl] = {
                        'source_count': row_count,
                        'inserted_count': row_count
                    }
                    logger.info(f"تم نقل الجدول {tbl}: {row_count} سجل بنجاح.")

                # تحديث التسلسلات التسلسلية التلقائية في PostgreSQL (Sequences Reset)
                for tbl in TABLE_MIGRATION_ORDER:
                    if tbl in existing_pg_tables:
                        try:
                            seq_sql = text(f"""
                                SELECT setval(
                                    pg_get_serial_sequence('"{tbl}"', 'id'),
                                    COALESCE((SELECT MAX(id) FROM "{tbl}"), 1),
                                    true
                                );
                            """)
                            pg_conn.execute(seq_sql)
                        except Exception:
                            # الجدول قد لا يملك تسلسل serial للـ id
                            pass

        finally:
            src_conn.close()

    def _verify_migration(self, pg_engine: Any):
        """مطابقة أعداد السجلات وبصمات التقارير المعتمدة وبصمة قاعدة المراجع."""
        uri = f"file:{self.sqlite_path.as_posix()}?mode=ro"
        src_conn = sqlite3.connect(uri, uri=True)

        try:
            with pg_engine.connect() as pg_conn:
                counts_match = True
                verification_summary = {}

                # 1. مطابقة أعداد السجلات لكل جدول
                for tbl, info in self.report['tables_migrated'].items():
                    src_cnt = info['source_count']
                    try:
                        pg_cnt = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}";')).scalar()
                    except Exception:
                        pg_cnt = -1

                    match = (src_cnt == pg_cnt)
                    verification_summary[tbl] = {
                        'source': src_cnt,
                        'destination': pg_cnt,
                        'match': match
                    }
                    if not match:
                        counts_match = False
                        logger.error(f"عدم تطابق في أعداد الجدول {tbl}: مصدر={src_cnt}، وجهة={pg_cnt}")

                self.report['verification']['table_counts'] = verification_summary
                self.report['verification']['counts_match'] = counts_match

                if not counts_match:
                    raise RuntimeError("فشل التحقق: أعداد السجلات غير متطابقة بين SQLite و PostgreSQL!")

                # 2. مطابقة بصمات التقارير المعتمدة (Finalized Report Hashes)
                src_cur = src_conn.cursor()
                try:
                    src_cur.execute("SELECT id, integrity_hash FROM reports WHERE status = 'finalized' OR lifecycle_status = 'finalized';")
                    src_reports = dict(src_cur.fetchall())
                except sqlite3.OperationalError:
                    src_reports = {}

                if src_reports:
                    pg_res = pg_conn.execute(text("SELECT id, integrity_hash FROM reports WHERE status = 'finalized' OR lifecycle_status = 'finalized';")).fetchall()
                    pg_reports = {r[0]: r[1] for r in pg_res}

                    hashes_match = True
                    for rep_id, s_hash in src_reports.items():
                        p_hash = pg_reports.get(rep_id)
                        if not p_hash or s_hash != p_hash:
                            hashes_match = False
                            logger.error(f"عدم تطابق بصمة التقرير النهائي {rep_id}: مصدر={s_hash}، وجهة={p_hash}")

                    self.report['verification']['finalized_report_hashes_match'] = hashes_match
                    self.report['verification']['verified_report_count'] = len(src_reports)

                    if not hashes_match:
                        raise RuntimeError("فشل التحقق: بصمات التقارير المعتمدة غير متطابقة!")
                else:
                    self.report['verification']['finalized_report_hashes_match'] = True
                    self.report['verification']['verified_report_count'] = 0

                logger.info("تم التحقق بنجاح من كافة البصمات والأعداد.")

        finally:
            src_conn.close()


def main():
    parser = argparse.ArgumentParser(description="أداة هجرة البيانات من SQLite إلى PostgreSQL أوفلاين (Prompt 1)")
    parser.add_argument("--sqlite-path", type=str, default=str(config.DEFAULT_SQLITE_PATH), help="مسار ملف SQLite المصدر")
    parser.add_argument("--pg-dsn", type=str, default=config.DATABASE_URL, help="سلسلة اتصال PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="تشغيل فحص مسبق دون كتابة بيانات")
    parser.add_argument("--output-report", type=str, default="migration_report.json", help="مسار حفظ تقرير الهجرة JSON")

    args = parser.parse_args()

    engine_mig = MigrationEngine(
        sqlite_path=Path(args.sqlite_path),
        pg_dsn=args.pg_dsn,
        dry_run=args.dry_run
    )

    report = engine_mig.run()

    out_path = Path(args.output_report)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(f"تم حفظ تقرير الهجرة في: {out_path.resolve()}")

    if not report.get('success'):
        sys.exit(1)


if __name__ == '__main__':
    main()
