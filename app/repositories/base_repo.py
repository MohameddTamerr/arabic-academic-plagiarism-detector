# -*- coding: utf-8 -*-
"""
طبقة الاتصال المركزية بقواعد البيانات (Database Engine & Session Management):
- تدعم SQLite محلياً حالياً مع الجاهزية التامة لـ PostgreSQL عبر DATABASE_URL.
- تدير دورة حياة الجلسات (Sessions) والتهيئة التلقائية للجداول.
- تهاجر البيانات القديمة من جدول papers إلى هيكل documents/pages/segments تلقائياً دون فقد أي بحث.
"""

import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, text, inspect, event
from sqlalchemy.orm import sessionmaker, Session
import shutil
from datetime import datetime

import config
from app.models.schema import Base, Document, DocumentPage, DocumentSegment, User
# استيراد النماذج الجديدة لضمان تضمينها في Base.metadata.create_all()
import app.models.research_schema  # noqa: F401  — side-effect import

logger = logging.getLogger(__name__)

# إعداد محرك SQLAlchemy
connect_args = {}
if config.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30.0}

engine = create_engine(
    config.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """تفعيل التحقق الصارم من المفاتيح الأجنبية (Foreign Keys) وضبط المهلة في SQLite."""
    if config.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA busy_timeout = 10000;")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_session():
    """Context manager لفتح وإغلاق جلسة قاعدة البيانات بأمان."""
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

    # ضبط إعدادات WAL والأداء لـ SQLite
    if config.DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode = WAL;"))
            conn.execute(text("PRAGMA synchronous = NORMAL;"))
            conn.execute(text("PRAGMA busy_timeout = 10000;"))
            conn.commit()

    # فحص وهجرة الأبحاث من الجدول القديم papers إذا وجد
    _migrate_legacy_papers_if_needed()

    # استعادة المهام المنقطعة: ScanBatchItems التي كانت running عند آخر إغلاق
    _recover_interrupted_batch_items()


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


def has_any_admin() -> bool:
    """التحقق مما إذا كان هناك حساب مدير مسجل في النظام."""
    with get_session() as session:
        return session.query(User).filter(User.role == 'admin').first() is not None
