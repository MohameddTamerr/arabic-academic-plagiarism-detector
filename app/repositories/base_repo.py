# -*- coding: utf-8 -*-
"""
طبقة الاتصال المركزية بقواعد البيانات (Database Engine & Session Management):
- تدعم SQLite محلياً حالياً مع الجاهزية التامة لـ PostgreSQL عبر DATABASE_URL.
- تدير دورة حياة الجلسات (Sessions) والتهيئة التلقائية للجداول.
- تهاجر البيانات القديمة من جدول papers إلى هيكل documents/pages/segments تلقائياً دون فقد أي بحث.
"""

import os
import logging
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine, text, inspect, event
from sqlalchemy.orm import sessionmaker, Session
import shutil
from datetime import datetime

import config
from app.models.schema import Base, Document, DocumentPage, DocumentSegment, User
# استيراد النماذج لضمان تضمينها في Base.metadata.create_all()
import app.models.research_schema  # noqa: F401
import app.models.audit_schema     # noqa: F401
import app.models.snapshot_schema  # noqa: F401
import app.models.backup_schema    # noqa: F401
import app.models.migration_schema # noqa: F401
import app.models.queue_schema     # noqa: F401

logger = logging.getLogger(__name__)


def get_backend_type(target_url: str = None) -> str:
    """استرجاع نوع محرك قاعدة البيانات النشط ('sqlite' أو 'postgresql')."""
    url = target_url or config.DATABASE_URL
    if url and (url.startswith("postgresql") or url.startswith("postgres")):
        return "postgresql"
    return "sqlite"


def _check_fail_safe(target_url: str):
    """صمام أمان لمنع الاختبارات الآلية من الاتصال بقاعدة البيانات الحية أبداً."""
    if os.environ.get('TESTING') == '1':
        b_type = get_backend_type(target_url)
        if b_type == "sqlite":
            db_path_str = target_url.replace("sqlite:///", "").replace("sqlite://", "")
            db_path_str = db_path_str.split('?')[0]
            try:
                resolved = Path(db_path_str).resolve()
                if resolved == config.LIVE_DEFAULT_SQLITE_PATH:
                    raise RuntimeError(
                        f"FAIL-SAFE GUARD ACTIVATED: Automated tests attempted to connect to the live production database! ({config.LIVE_DEFAULT_SQLITE_PATH})"
                    )
            except Exception as e:
                if isinstance(e, RuntimeError):
                    raise e
        elif b_type == "postgresql":
            # التحقق من أن اسم قاعدة البيانات في بيئة الاختبار يحتوي على 'test'
            db_name = target_url.split('/')[-1].split('?')[0]
            if 'test' not in db_name.lower():
                raise RuntimeError(
                    f"FAIL-SAFE GUARD ACTIVATED: Automated tests must use a test database containing 'test' in its name, got: {db_name}"
                )

# فحص الأمان المبدئي
_check_fail_safe(config.DATABASE_URL)


def _create_configured_engine(db_url: str):
    _check_fail_safe(db_url)
    b_type = get_backend_type(db_url)

    if b_type == "sqlite":
        connect_args = {"check_same_thread": False, "timeout": 30.0}
        new_engine = create_engine(
            db_url,
            connect_args=connect_args,
            pool_pre_ping=True
        )

        @event.listens_for(new_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("PRAGMA journal_mode = WAL;")
            cursor.execute("PRAGMA synchronous = NORMAL;")
            cursor.execute("PRAGMA busy_timeout = 10000;")
            cursor.execute("PRAGMA temp_store = MEMORY;")
            cursor.execute("PRAGMA wal_autocheckpoint = 1000;")
            cursor.close()

    else:
        # إعداد محرك PostgreSQL مع مجمع اتصالات منضبط
        new_engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=getattr(config, 'DB_POOL_SIZE', 10),
            max_overflow=getattr(config, 'DB_MAX_OVERFLOW', 20),
            pool_timeout=getattr(config, 'DB_POOL_TIMEOUT', 30),
            pool_recycle=getattr(config, 'DB_POOL_RECYCLE', 1800)
        )

    return new_engine


engine = _create_configured_engine(config.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def rebind_engine(new_database_url: str = None):
    """إعادة ربط المحرك المركزي بقاعدة بيانات جديدة (مستخدم في بيئات الاختبار المعزولة)."""
    global engine, SessionLocal
    if new_database_url:
        config.DATABASE_URL = new_database_url
    if engine:
        engine.dispose()
    engine = _create_configured_engine(config.DATABASE_URL)
    SessionLocal.configure(bind=engine)
    return engine


@contextmanager
def get_session():
    """Context manager لفتح وإغلاق جلسة قاعدة البيانات بأمان تام."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_database():
    """
    إنشاء كافة الجداول وترقية الهيكل القديم ونقل البيانات بسلاسة.
    """
    logger.info("جاري تهيئة قاعدة البيانات والتأكد من الجداول...")
    Base.metadata.create_all(bind=engine)

    # تطبيق هجرات الهيكل الرسمية عبر سجل الهجرات
    from app.services.migration_service import apply_all_migrations
    apply_all_migrations()

    # فحص وهجرة الأبحاث من الجدول القديم papers إذا وجد
    _migrate_legacy_papers_if_needed()

    # هجرة وتعيين الأرقام المرجعية الرسمية للأبحاث
    _migrate_research_reference_numbers()

    # هجرة وفصل حالات الفحص والتحكيم (Phase 5 Status Migration)
    _migrate_workflow_statuses()

    # استعادة المهام المنقطعة: ScanBatchItems التي كانت running عند آخر إغلاق
    _recover_interrupted_batch_items()


init_db = init_database


def _migrate_workflow_statuses():
    """
    هجرة الحالات المنفصلة (Workflow Status Migration):
    - إضافة أعمدة scan_status و review_status لجداولي research و reports إذا لم تكن موجودة.
    - تحويل الحالات السابقة المختلطة عبر map_legacy_status().
    """
    try:
        from app.workflow.statuses import map_legacy_status
        from app.models.research_schema import Research
        from app.models.schema import LegacyReport

        inspector = inspect(engine)
        table_names = inspector.get_table_names()

        # 1. فحص جدول reports
        if 'reports' in table_names:
            rep_cols = [c['name'] for c in inspector.get_columns('reports')]
            with engine.connect() as conn:
                if 'scan_status' not in rep_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN scan_status VARCHAR(50) DEFAULT 'completed';"))
                if 'review_status' not in rep_cols:
                    conn.execute(text("ALTER TABLE reports ADD COLUMN review_status VARCHAR(50) DEFAULT 'pending_review';"))
                conn.commit()

        # 2. فحص جدول research
        if 'research' in table_names:
            res_cols = [c['name'] for c in inspector.get_columns('research')]
            with engine.connect() as conn:
                if 'scan_status' not in res_cols:
                    conn.execute(text("ALTER TABLE research ADD COLUMN scan_status VARCHAR(50) DEFAULT 'queued';"))
                if 'review_status' not in res_cols:
                    conn.execute(text("ALTER TABLE research ADD COLUMN review_status VARCHAR(50) DEFAULT 'pending_review';"))
                conn.commit()

        # 3. هجرة البيانات
        with get_session() as session:
            # هجرة التقارير
            reps = session.query(LegacyReport).all()
            for r in reps:
                if not r.scan_status or not r.review_status:
                    s_stat, r_stat = map_legacy_status(r.status)
                    r.scan_status = s_stat
                    r.review_status = r_stat

            # هجرة الأبحاث
            researches = session.query(Research).all()
            for res in researches:
                if not res.scan_status or not res.review_status:
                    if res.report_id:
                        matched_rep = session.query(LegacyReport).filter(LegacyReport.id == res.report_id).first()
                        if matched_rep:
                            res.scan_status = matched_rep.scan_status or 'completed'
                            res.review_status = matched_rep.review_status or 'pending_review'
                        else:
                            res.scan_status = 'completed'
                            res.review_status = 'pending_review'
                    else:
                        res.scan_status = 'queued'
                        res.review_status = 'pending_review'

    except Exception as e:
        logger.error(f"خطأ أثناء هجرة حالات سير العمل (Workflow Status Migration): {e}")


def _migrate_legacy_papers_if_needed():
    """
    التحقق من وجود جدول papers القديم ونقل الأبحاث إلى documents إذا لم تكن منقولة مع أخذ نسخة احتياطية أولاً.
    """
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if 'papers' in table_names:
        logger.info("تم العثور على جدول أبحاث قديم (papers). جاري التحقق من الهجرة...")
        # أخذ نسخة احتياطية آمنة من ملف قاعدة البيانات قبل الهجرة
        if config.DATABASE_URL.startswith("sqlite"):
            try:
                db_file = config.DEFAULT_SQLITE_PATH
                if db_file.exists():
                    bak_path = db_file.parent / f"{db_file.name}.bak_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    shutil.copy2(db_file, bak_path)
                    logger.info(f"تم إنشاء نسخة احتياطية لقاعدة البيانات قبل الهجرة في: {bak_path}")
            except Exception as e:
                logger.warning(f"تعذر أخذ نسخة احتياطية قبل الهجرة: {e}")

        try:
            with get_session() as session:
                doc_count = session.query(Document).count()
                if doc_count == 0:
                    # قراءة السجلات القديمة
                    result = session.execute(text("SELECT id, title, author, file_path, full_text, category, added_at FROM papers"))
                    rows = result.fetchall()
                    from plagiarism_detector.preprocessing.normalizer import normalize_light, split_sentences
                    from plagiarism_detector.preprocessing.segmenter import DocumentSegment
                    import hashlib

                    for r in rows:
                        pid, title, author, fpath, ftext, cat, added_at = r
                        f_hash = hashlib.sha256(ftext.encode('utf-8')).hexdigest()
                        doc = Document(
                            title=title,
                            author=author or '',
                            file_path=fpath or '',
                            file_hash=f_hash,
                            category=cat or 'عام'
                        )
                        session.add(doc)
                        session.flush()

                        # إنشاء صفحة وحيدة افتراضية للمستندات القديمة
                        p = DocumentPage(
                            document_id=doc.id,
                            page_number=None,
                            raw_text=ftext,
                            normalized_text=normalize_light(ftext)
                        )
                        session.add(p)

                        # تقطيع الجمل
                        sents = split_sentences(ftext, min_words=4)
                        for s_idx, sent in enumerate(sents):
                            seg = DocumentSegment(
                                document_id=doc.id,
                                page_number=None,
                                segment_number=s_idx + 1,
                                raw_text=sent,
                                normalized_text=normalize_light(sent),
                                word_count=len(sent.split())
                            )
                            session.add(seg)

                    logger.info(f"تمت هجرة {len(rows)} بحثاً قديماً بنجاح إلى الهيكل الجديد.")
        except Exception as e:
            logger.error(f"خطأ أثناء هجرة البيانات القديمة: {e}")


def _recover_interrupted_batch_items():
    """
    عند إعادة تشغيل الخادم: تمييز مهام الدفعة المنقطعة كـ 'interrupted'
    لتمكين إعادة الفحص يدوياً — لا نُعيّنها 'completed' بصمت.
    """
    try:
        from app.models.research_schema import ScanBatchItem, ScanBatch
        with get_session() as session:
            interrupted = session.query(ScanBatchItem).filter(
                ScanBatchItem.status.in_(['running', 'queued'])
            ).all()
            for item in interrupted:
                item.status = 'interrupted'
                item.error_message = 'أُعيد تشغيل الخادم أثناء المعالجة — يرجى إعادة الفحص.'
            if interrupted:
                # تحديث حالة الدفعات المتأثرة
                affected_batch_ids = {item.batch_id for item in interrupted}
                for bid in affected_batch_ids:
                    batch = session.query(ScanBatch).filter(ScanBatch.id == bid).first()
                    if batch and batch.status == 'running':
                        batch.status = 'partial'
                logger.info(f"تم تمييز {len(interrupted)} مهمة منقطعة كـ interrupted عند إعادة التشغيل.")
    except Exception as e:
        logger.warning(f"تعذر استعادة المهام المنقطعة: {e}")


def _migrate_research_reference_numbers():
    """
    التحقق من وجود عمود reference_number في جدول research وتوليد أرقام مرجعية تاريخية ثابتة
    لجميع الأبحاث القديمة التي ليس لها رقم مرجعي، مرتبة حسب تاريخ الإنشاء ثم الـ id.
    """
    try:
        from app.models.research_schema import Research, ReferenceSequence
        from app.services.reference_service import format_reference_number

        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        if 'research' not in table_names:
            return

        cols = [c['name'] for c in inspector.get_columns('research')]
        if 'reference_number' not in cols:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE research ADD COLUMN reference_number VARCHAR(50);"))
                conn.commit()
            logger.info("تمت إضافة عمود reference_number إلى جدول research.")

        with get_session() as session:
            unreferenced = (
                session.query(Research)
                .filter((Research.reference_number == None) | (Research.reference_number == ''))
                .order_by(Research.created_at.asc(), Research.id.asc())
                .all()
            )

            if unreferenced:
                if config.DATABASE_URL.startswith("sqlite"):
                    try:
                        db_file = config.DEFAULT_SQLITE_PATH
                        if db_file.exists():
                            bak_path = db_file.parent / f"{db_file.name}.bak_refnum_mig_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            shutil.copy2(db_file, bak_path)
                            logger.info(f"تم إنشاء نسخة احتياطية قبل هجرة الأرقام المرجعية في: {bak_path}")
                    except Exception as e:
                        logger.warning(f"تعذر أخذ نسخة احتياطية: {e}")

                prefix = getattr(config, 'RESEARCH_REFERENCE_PREFIX', 'RES')
                for res in unreferenced:
                    res_year = res.created_at.year if res.created_at else datetime.utcnow().year
                    seq_rec = (
                        session.query(ReferenceSequence)
                        .filter(
                            ReferenceSequence.namespace == 'research',
                            ReferenceSequence.year == res_year
                        )
                        .first()
                    )
                    if not seq_rec:
                        seq_rec = ReferenceSequence(
                            namespace='research',
                            year=res_year,
                            last_value=1,
                            updated_at=datetime.utcnow()
                        )
                        session.add(seq_rec)
                        session.flush()
                        seq_val = 1
                    else:
                        seq_rec.last_value += 1
                        seq_rec.updated_at = datetime.utcnow()
                        session.flush()
                        seq_val = seq_rec.last_value

                    res.reference_number = format_reference_number(prefix, res_year, seq_val)

                logger.info(f"تم تعيين أرقام مرجعية رسمية لـ {len(unreferenced)} بحثاً تاريخياً بنجاح.")
    except Exception as e:
        logger.error(f"خطأ أثناء هجرة الأرقام المرجعية للأبحاث: {e}")


def has_any_admin() -> bool:
    """التحقق مما إذا كان هناك حساب مدير مسجل في النظام."""
    with get_session() as session:
        return session.query(User).filter(User.role == 'admin').first() is not None
