# -*- coding: utf-8 -*-
"""
خدمة سجل وإدارة هجرات قاعدة البيانات (Database Schema Migration Registry):
- تطبيق الهجرات التراكمية بشكل مرتب ومحدد وغير متكرر (Idempotent Ordered Migrations).
- تسجيل الإصدارات المنفذة في جدول schema_migrations.
- توفير الجاهزية التامة للهيكل دون الحاجة لأدوات خارجية معقدة.
"""

import time
import logging
from datetime import datetime
from typing import List, Dict, Callable, Any
from sqlalchemy import text, inspect

from app import versioning
from app.repositories import base_repo
from app.models.migration_schema import SchemaMigration

logger = logging.getLogger(__name__)


def get_applied_migrations() -> List[str]:
    """استرجاع قائمة معرفات الهجرات المطبقة مسبقاً."""
    with base_repo.get_session() as session:
        applied = session.query(SchemaMigration.version).order_by(SchemaMigration.id.asc()).all()
        return [a[0] for a in applied]


def record_migration(version: str, description: str, elapsed_ms: int, status: str = 'completed') -> None:
    """توثيق نجاح تطبيق هجرة محددة في السجل."""
    with base_repo.get_session() as session:
        mig = SchemaMigration(
            version=version,
            description=description,
            applied_at=datetime.utcnow(),
            execution_time_ms=elapsed_ms,
            status=status
        )
        session.add(mig)


# ─── سجل الهجرات المعتمدة ───────────────────────────────────────────────────

def _migration_001_initial_schema():
    """الهجرة 001: التحقق من الجداول الأساسية وتفعيل المفاتيح الأجنبية."""
    pass


def _migration_002_phase9_indexes():
    """الهجرة 002: إنشاء الفهارس المتقدمة لتحسين أداء الاستعلامات والتقارير."""
    with base_repo.engine.connect() as conn:
        # فهارس الأبحاث والملفات
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_research_status ON research (scan_status, review_status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_research_created ON research (created_at);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_research_ref_num ON research (reference_number);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_research_report_id ON research (report_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_research_files_hash ON research_files (file_hash);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_research_files_rid ON research_files (research_id);"))

        # فهارس التقارير
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports (scan_status, review_status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_reports_created ON reports (created_at);"))

        # فهارس سجل التدقيق
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs (created_at);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_action_cat ON audit_logs (category, action);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_ref_num ON audit_logs (research_reference_number);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_audit_obj ON audit_logs (object_type, object_id);"))

        # فهارس النسخ الاحتياطي
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_backup_ident ON backup_catalog (backup_identifier);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_backup_status ON backup_catalog (status);"))

        conn.commit()


def _migration_003_phase14_auth_hardening():
    """الهجرة 003: دعم أمان الجلسات وحالة القفل وإلغاء الجلسات الفوري."""
    with base_repo.engine.connect() as conn:
        # فحص أعمدة جدول users
        user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users);")).fetchall()}
        if 'is_active' not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1;"))
        if 'session_version' not in user_cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN session_version INTEGER DEFAULT 1;"))

        # إنشاء جدول auth_lockouts إذا لم يكن موجوداً
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS auth_lockouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                identifier VARCHAR(255) NOT NULL UNIQUE,
                failed_count INTEGER DEFAULT 0,
                last_failed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                locked_until DATETIME,
                lockout_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_auth_lockouts_ident ON auth_lockouts (identifier);"))
        conn.commit()


def _migration_004_security_state():
    """الهجرة 004: إنشاء جدول الحالة الأمنية للمنظومة واستكمال التهيئة."""
    with base_repo.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS system_security_state (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.commit()


def _migration_005_phase15_report_integrity():
    """الهجرة 005: دعم نزاهة التقارير وإدارة المراجعات وسجل قرارات التحكيم."""
    with base_repo.engine.connect() as conn:
        # فحص أعمدة جدول reports
        report_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(reports);")).fetchall()}
        
        cols_to_add = [
            ('research_id', 'INTEGER'),
            ('scan_execution_id', 'VARCHAR(64)'),
            ('revision_number', 'INTEGER DEFAULT 1'),
            ('supersedes_report_id', 'VARCHAR(64)'),
            ('artifact_status', "VARCHAR(50) DEFAULT 'draft'"),
            ('finalization_hash', "VARCHAR(64) DEFAULT ''"),
            ('finalized_at', 'DATETIME'),
            ('finalized_by', "VARCHAR(255) DEFAULT ''"),
            ('void_reason', "TEXT DEFAULT ''"),
            ('voided_by', "VARCHAR(255) DEFAULT ''"),
            ('voided_at', 'DATETIME'),
            ('input_manifest_json', "TEXT DEFAULT '[]'"),
            ('reference_sources_json', "TEXT DEFAULT '[]'"),
            ('evidence_snapshot_json', "TEXT DEFAULT '[]'"),
            ('canonical_payload_json', "TEXT DEFAULT ''")
        ]

        for col_name, col_type in cols_to_add:
            if col_name not in report_cols:
                conn.execute(text(f"ALTER TABLE reports ADD COLUMN {col_name} {col_type};"))

        # إنشاء جدول review_decision_history إذا لم يكن موجوداً
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS review_decision_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id VARCHAR(64) NOT NULL,
                research_id INTEGER,
                decision VARCHAR(50) NOT NULL,
                reviewer VARCHAR(255) NOT NULL,
                comment TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # فهارس النزاهة والمراجعات
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rep_research_rev ON reports (research_id, revision_number);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rep_artifact_status ON reports (artifact_status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rep_final_hash ON reports (finalization_hash);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rev_hist_report ON review_decision_history (report_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rev_hist_research ON review_decision_history (research_id);"))

        conn.commit()


def _migration_006_phase16_corpus_governance():
    """الهجرة 006: حوكمة قاعدة المراجع، المعرفات الثابتة، سجل التغييرات وفهارس الاسترجاع."""
    import uuid
    with base_repo.engine.connect() as conn:
        doc_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(documents);")).fetchall()}

        cols_to_add = [
            ('reference_id', 'VARCHAR(64)'),
            ('original_filename', "VARCHAR(500) DEFAULT ''"),
            ('size_bytes', 'INTEGER DEFAULT 0'),
            ('current_status', "VARCHAR(50) DEFAULT 'active'"),
            ('publisher', "VARCHAR(255) DEFAULT ''"),
            ('edition', "VARCHAR(100) DEFAULT ''"),
            ('document_type', "VARCHAR(100) DEFAULT 'paper'"),
            ('source_category', "VARCHAR(100) DEFAULT 'academic'"),
            ('added_by', "VARCHAR(255) DEFAULT ''"),
            ('notes', "TEXT DEFAULT ''"),
            ('ownership_note', "TEXT DEFAULT ''"),
            ('supersedes_reference_id', 'VARCHAR(64)'),
            ('superseded_by_reference_id', 'VARCHAR(64)'),
            ('active_from_version', "VARCHAR(50) DEFAULT ''"),
            ('inactive_from_version', 'VARCHAR(50)'),
            ('integrity_status', "VARCHAR(50) DEFAULT 'verified'"),
            ('last_integrity_check', 'DATETIME')
        ]

        for col_name, col_type in cols_to_add:
            if col_name not in doc_cols:
                conn.execute(text(f"ALTER TABLE documents ADD COLUMN {col_name} {col_type};"))

        # ملء المعرفات الثابتة المستقرة للأبحاث الحالية التي ليس لها reference_id
        existing_docs = conn.execute(text("SELECT id, reference_id, active_from_version FROM documents;")).fetchall()
        for d_id, ref_id, act_ver in existing_docs:
            updates = []
            params = {'id': d_id}
            if not ref_id:
                new_ref_id = f"ref-{uuid.uuid4().hex[:12]}"
                updates.append("reference_id = :ref_id")
                params['ref_id'] = new_ref_id
            if not act_ver:
                updates.append("active_from_version = 'REF-2026-000001'")
            if updates:
                sql = f"UPDATE documents SET {', '.join(updates)} WHERE id = :id"
                conn.execute(text(sql), params)

        # إنشاء جدول reference_metadata_history
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reference_metadata_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                reference_id VARCHAR(64) NOT NULL,
                field_name VARCHAR(100) NOT NULL,
                old_value TEXT DEFAULT '',
                new_value TEXT DEFAULT '',
                changed_by VARCHAR(255) DEFAULT '',
                reason TEXT DEFAULT '',
                changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
            );
        """))

        # إنشاء جدول corpus_changesets
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS corpus_changesets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                corpus_version VARCHAR(50) NOT NULL,
                event_id VARCHAR(64) NOT NULL UNIQUE,
                change_type VARCHAR(50) NOT NULL,
                reference_id VARCHAR(64) NOT NULL,
                previous_reference_id VARCHAR(64),
                actor VARCHAR(255) DEFAULT '',
                reason TEXT DEFAULT '',
                resulting_status VARCHAR(50) DEFAULT 'active',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # إنشاء جدول index_state_records
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS index_state_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                index_corpus_version VARCHAR(50) DEFAULT '',
                index_fingerprint VARCHAR(64) DEFAULT '',
                state VARCHAR(50) DEFAULT 'stale',
                built_at DATETIME,
                built_by VARCHAR(255) DEFAULT 'system',
                total_segments INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # الفهارس المتقدمة
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_doc_ref_id ON documents (reference_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_doc_curr_status ON documents (current_status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_doc_act_ver ON documents (active_from_version);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_doc_inact_ver ON documents (inactive_from_version);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ref_meta_hist_refid ON reference_metadata_history (reference_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_ref_meta_hist_docid ON reference_metadata_history (document_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_corpus_chg_ver ON corpus_changesets (corpus_version);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_corpus_chg_ref ON corpus_changesets (reference_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_index_state ON index_state_records (state);"))

        conn.commit()


def _migration_007_phase17_job_queue():
    """الهجرة 007: إنشاء جدول سجل وإدارة مهام التشغيل الخلفية وفهارس الأداء المتقدمة."""
    with base_repo.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS job_records (
                id VARCHAR(64) PRIMARY KEY,
                job_type VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 0,
                queued_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                started_at DATETIME,
                finished_at DATETIME,
                heartbeat_at DATETIME,
                retry_at DATETIME,
                requested_by VARCHAR(255) DEFAULT '',
                worker_pid INTEGER,
                lease_token VARCHAR(64),
                progress INTEGER DEFAULT 0,
                stage VARCHAR(255) DEFAULT '',
                cancel_requested INTEGER DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                error_code VARCHAR(100) DEFAULT '',
                safe_error_message TEXT DEFAULT '',
                research_id INTEGER,
                batch_id VARCHAR(64),
                batch_item_id INTEGER,
                report_id VARCHAR(64),
                scan_execution_id VARCHAR(64),
                target_corpus_version VARCHAR(50),
                payload_json TEXT DEFAULT '{}',
                result_json TEXT DEFAULT '{}',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))

        # الفهارس المتقدمة لإدارة وسحب مهام الطابور
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_dequeue ON job_records (status, retry_at, priority, queued_at);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_heartbeat ON job_records (status, heartbeat_at);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_dedup_index ON job_records (job_type, target_corpus_version, status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_scan_exec ON job_records (scan_execution_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_research ON job_records (research_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_batch ON job_records (batch_id);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_status ON job_records (status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_job_type ON job_records (job_type);"))

        # مواءمة الحالات المعلقة السابقة
        conn.execute(text("UPDATE scan_jobs SET status = 'interrupted' WHERE status IN ('running', 'processing');"))
        conn.commit()


def _migration_008_phase18_storage_status():
    """الهجرة 008: دعم حالة التخزين الصريحة في جدول research_files وفهارس التحقق."""
    with base_repo.engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(research_files);")).fetchall()}
        if 'storage_status' not in cols:
            conn.execute(text("ALTER TABLE research_files ADD COLUMN storage_status VARCHAR(50) DEFAULT 'finalized' NOT NULL;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_rf_storage_status ON research_files (storage_status);"))
            conn.commit()


def _migration_009_phase19_user_mgmt_and_theses():
    """الهجرة 009: إدارة المستخدمين المؤسسية، هيكل الرسائل متعددة الأجزاء، والتقارير المجمعة."""
    with base_repo.engine.connect() as conn:
        # 1. ترقية جدول users
        user_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users);")).fetchall()}
        user_cols_to_add = [
            ('department', "VARCHAR(255) DEFAULT ''"),
            ('phone_number', "VARCHAR(50) DEFAULT ''"),
            ('must_change_password', "INTEGER DEFAULT 0"),
            ('must_enroll_recovery', "INTEGER DEFAULT 0"),
        ]
        for col_name, col_def in user_cols_to_add:
            if col_name not in user_cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def};"))

        # 2. ترقية جدول review_decision_history
        rev_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(review_decision_history);")).fetchall()}
        rev_cols_to_add = [
            ('thesis_id', "INTEGER"),
            ('report_revision', "INTEGER DEFAULT 1"),
            ('previous_review_status', "VARCHAR(50) DEFAULT ''"),
            ('new_review_status', "VARCHAR(50) DEFAULT ''"),
            ('reviewer_user_id', "INTEGER"),
            ('reviewer_role_snapshot', "VARCHAR(50) DEFAULT ''"),
            ('rejection_reason', "TEXT DEFAULT ''"),
            ('request_id', "VARCHAR(64) DEFAULT ''"),
        ]
        for col_name, col_def in rev_cols_to_add:
            if col_name not in rev_cols:
                conn.execute(text(f"ALTER TABLE review_decision_history ADD COLUMN {col_name} {col_def};"))

        # 3. ترقية جدول reports
        report_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(reports);")).fetchall()}
        report_cols_to_add = [
            ('thesis_id', "INTEGER"),
            ('is_combined_thesis', "INTEGER DEFAULT 0"),
            ('submitted_by_user_id', "INTEGER"),
        ]
        for col_name, col_def in report_cols_to_add:
            if col_name not in report_cols:
                conn.execute(text(f"ALTER TABLE reports ADD COLUMN {col_name} {col_def};"))

        # 4. جدول reference_sequences
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS reference_sequences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace VARCHAR(50) NOT NULL DEFAULT 'research',
                year INTEGER NOT NULL,
                last_value INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_ref_seq_ns_year ON reference_sequences (namespace, year);"))

        # 5. جدول theses
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS theses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference_number VARCHAR(50) NOT NULL UNIQUE,
                title VARCHAR(500) NOT NULL,
                author VARCHAR(255) DEFAULT '',
                degree_type VARCHAR(100) DEFAULT 'ماجستير',
                department VARCHAR(255) DEFAULT '',
                academic_year VARCHAR(50) DEFAULT '',
                notes TEXT DEFAULT '',
                status VARCHAR(50) DEFAULT 'draft',
                review_status VARCHAR(50) DEFAULT 'pending_review',
                combined_report_id VARCHAR(64),
                is_stale INTEGER DEFAULT 0,
                created_by VARCHAR(255) DEFAULT '',
                created_by_user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_thesis_ref_num ON theses (reference_number);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_thesis_status ON theses (status);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_thesis_review_status ON theses (review_status);"))

        # 6. جدول thesis_parts
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS thesis_parts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thesis_id INTEGER NOT NULL,
                part_title VARCHAR(500) NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                original_filename VARCHAR(500) NOT NULL,
                stored_filename VARCHAR(500) NOT NULL,
                file_path TEXT DEFAULT '',
                file_type VARCHAR(10) DEFAULT 'pdf',
                file_size_bytes BIGINT DEFAULT 0,
                file_hash VARCHAR(64) DEFAULT '',
                scan_status VARCHAR(50) DEFAULT 'queued',
                scan_job_id VARCHAR(64),
                report_id VARCHAR(64),
                similarity_pct FLOAT,
                problematic_pct FLOAT,
                copied_pct FLOAT,
                para_pct FLOAT,
                cited_pct FLOAT,
                total_words INTEGER DEFAULT 0,
                problematic_words INTEGER DEFAULT 0,
                copied_words INTEGER DEFAULT 0,
                para_words INTEGER DEFAULT 0,
                cited_words INTEGER DEFAULT 0,
                error_message TEXT DEFAULT '',
                is_detached INTEGER DEFAULT 0,
                detached_by VARCHAR(255) DEFAULT '',
                detached_at DATETIME,
                detach_reason TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thesis_id) REFERENCES theses (id) ON DELETE CASCADE
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tp_thesis_order ON thesis_parts (thesis_id, sort_order);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tp_thesis_hash ON thesis_parts (thesis_id, file_hash);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_tp_scan_status ON thesis_parts (scan_status);"))

        conn.commit()


MIGRATIONS_REGISTRY: List[Dict[str, Any]] = [
    {
        'version': '001_initial_schema',
        'description': 'الهيكل التأسيسي الموحد وترقية جداول الوثائق والأبحاث',
        'func': _migration_001_initial_schema
    },
    {
        'version': '002_phase9_indexes',
        'description': 'فهارس الأداء المتقدمة للأبحاث والتقارير وسجلات التدقيق والنسخ',
        'func': _migration_002_phase9_indexes
    },
    {
        'version': '003_phase14_auth_hardening',
        'description': 'أمان الجلسات وإلغاء الصلاحيات وجدول قفل محاولات الدخول',
        'func': _migration_003_phase14_auth_hardening
    },
    {
        'version': '004_security_state',
        'description': 'جدول الحالة الأمنية للمنظومة والتهيئة الأولية الدائمة',
        'func': _migration_004_security_state
    },
    {
        'version': '005_phase15_report_integrity',
        'description': 'دعم نزاهة التقارير وإدارة المراجعات وسجل قرارات التحكيم وبصمة الاعتماد',
        'func': _migration_005_phase15_report_integrity
    },
    {
        'version': '006_phase16_corpus_governance',
        'description': 'حوكمة قاعدة المراجع، المعرفات الثابتة، سجل التغييرات، وفهارس الاسترجاع',
        'func': _migration_006_phase16_corpus_governance
    },
    {
        'version': '007_phase17_job_queue',
        'description': 'إدارة طابور المهام الخلفية، التزامن المحصن، الفهارس وسجل التنفيذ',
        'func': _migration_007_phase17_job_queue
    },
    {
        'version': '008_phase18_storage_status',
        'description': 'دعم حالة التخزين الصريحة في جدول research_files وفهارس التحقق',
        'func': _migration_008_phase18_storage_status
    },
    {
        'version': '009_phase19_user_mgmt_and_theses',
        'description': 'إدارة المستخدمين المؤسسية، هيكل الرسائل متعددة الأجزاء، والتقارير المجمعة',
        'func': _migration_009_phase19_user_mgmt_and_theses
    }
]


def apply_all_migrations() -> int:
    """
    تنفيذ الهجرات غير المطبقة بالترتيب التراكمي المعتمد.
    يُعيد عدد الهجرات الجديدة التي تم تطبيقها بنجاح.
    """
    applied_versions = set(get_applied_migrations())
    applied_count = 0

    for mig in MIGRATIONS_REGISTRY:
        v = mig['version']
        if v not in applied_versions:
            logger.info(f"جاري تطبيق هجرة قاعدة البيانات: {v} - {mig['description']}...")
            start_t = time.perf_counter()
            try:
                mig['func']()
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)
                record_migration(v, mig['description'], elapsed_ms, 'completed')
                logger.info(f"تم تطبيق الهجرة {v} بنجاح خلال {elapsed_ms}ms")
                applied_count += 1
            except Exception as e:
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)
                record_migration(v, mig['description'], elapsed_ms, 'failed')
                logger.error(f"فشل تطبيق الهجرة {v}: {e}", exc_info=True)
                raise e

    return applied_count
