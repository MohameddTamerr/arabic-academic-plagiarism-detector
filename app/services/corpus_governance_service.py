# -*- coding: utf-8 -*-
"""
خدمة حوكمة وتتبع وإصدارات قاعدة المراجع المؤسسية (Reference Corpus Governance Service):
- الهوية المستقرة للمراجع (Immutable Stable Reference ID / UUID).
- دورة حياة المراجع (active, superseded, retired, invalid).
- التتبع المؤسسي والبيانات الوصفية وسجل التعديلات (Metadata Revision History).
- الإصدارات التراكمية الذرية الموحدة وسجل التغييرات (Corpus Changesets & Monotonic Versioning).
- البصمة الرقمية الحتمية والمستقرة عبر الهجرات (Migration-Stable Deterministic Fingerprint).
- استنساخ عضوية قاعدة المراجع تاريخياً (Historical Corpus Membership Reconstruction).
- التحقق من النزاهة وحماية التقارير السابقة من التعديل أو الحذف.
"""

import os
import uuid
import hashlib
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from sqlalchemy import text, or_

import config
from app.errors.error_codes import ErrorCode
from app.models.schema import (
    Document, DocumentPage, DocumentSegment,
    ReferenceMetadataHistory, CorpusChangeset, IndexStateRecord
)
from app.models.snapshot_schema import ReferenceCorpusVersion
from app.repositories.base_repo import get_session
from app.services import reference_service, audit_service, integrity_service
from plagiarism_detector.preprocessing.normalizer import normalize_light, normalize_aggressive
from plagiarism_detector.extraction.page_extractor import extract_document_pages
from plagiarism_detector.preprocessing.segmenter import segment_pages
from plagiarism_detector.core.categorizer import categorize_text

logger = logging.getLogger(__name__)

STATUS_ACTIVE = "active"
STATUS_SUPERSEDED = "superseded"
STATUS_RETIRED = "retired"
STATUS_INVALID = "invalid"

STATUS_LABELS_AR = {
    STATUS_ACTIVE: "نشط",
    STATUS_SUPERSEDED: "تم استبداله",
    STATUS_RETIRED: "موقوف",
    STATUS_INVALID: "غير صالح"
}


def compute_deterministic_corpus_fingerprint(session=None) -> Tuple[str, int]:
    """
    حساب البصمة الرقمية الحتمية والمستقرة (Migration-Stable Deterministic Fingerprint)
    لكافة المراجع المعتمدة النشطة (active).
    - تعتمد حصراً على عضوية المراجع الفعالة وهويتها المستقرة: (reference_id, file_hash).
    - لا تعتمد على المعرفات الرقمية التلقائية (Auto-increment integer IDs) أو الحقول المؤقتة.
    - الترتيب الأبجدي الحتمي لـ reference_id يضمن تطابق البصمة عند استعادة النسخ أو النقل.
    - الترميز: UTF-8 لسلسلة "{reference_id}:{file_hash};" المتتالية.
    """
    def _calculate(s) -> Tuple[str, int]:
        docs = (
            s.query(Document.reference_id, Document.file_hash)
            .filter(Document.current_status == STATUS_ACTIVE)
            .order_by(Document.reference_id.asc())
            .all()
        )
        doc_count = len(docs)
        if not docs:
            return hashlib.sha256(b"EMPTY_CORPUS").hexdigest(), 0

        hasher = hashlib.sha256()
        for ref_id, f_hash in docs:
            entry = f"{ref_id}:{f_hash or ''};"
            hasher.update(entry.encode('utf-8'))
        return hasher.hexdigest(), doc_count

    if session:
        return _calculate(session)
    with get_session() as s:
        return _calculate(s)


def mark_index_stale(corpus_version: str = '', session=None) -> None:
    """
    تعليم فهرس الاسترجاع بأنه غير متطابق (stale) عند حدوث أي تغيير مؤثر في قاعدة المراجع.
    """
    def _mark(s):
        latest = s.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
        if not latest:
            rec = IndexStateRecord(
                index_corpus_version=corpus_version,
                state='stale',
                built_at=None,
                updated_at=datetime.utcnow()
            )
            s.add(rec)
        else:
            latest.state = 'stale'
            latest.updated_at = datetime.utcnow()

    # تحديث الكاش في الذاكرة
    try:
        from plagiarism_detector.reporting import report_builder
        report_builder.invalidate_pipeline_index(mark_stale_in_db=False)
    except Exception:
        pass

    if session:
        _mark(session)
    else:
        with get_session() as s:
            _mark(s)


def allocate_corpus_version(
    change_type: str,
    reference_id: str,
    actor: str = 'system',
    reason: str = '',
    previous_reference_id: Optional[str] = None,
    resulting_status: str = STATUS_ACTIVE,
    session=None
) -> str:
    """
    حجز وتوليد إصدار جديد لقاعدة المراجع ذرياً عبر العمليات المتعددة (Multi-Process Atomic Allocation):
    - يسجل المعرف التسلسلي المتزايد REF-YYYY-XXXXXX.
    - يحسب البصمة الرقمية الحتمية ويسجل ReferenceCorpusVersion.
    - يسجل حركة التغيير في جدول corpus_changesets.
    - يعلم فهرس الاسترجاع كـ stale.
    """
    year = datetime.now().year
    next_seq = reference_service.get_next_sequence_value('reference_corpus', year)
    version_id = f"REF-{year}-{next_seq:06d}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"

    def _execute(s) -> str:
        fp, count = compute_deterministic_corpus_fingerprint(session=s)

        # 1. تسجيل سجل إصدار قاعدة المراجع
        ver_rec = ReferenceCorpusVersion(
            version_identifier=version_id,
            fingerprint=fp,
            document_count=count,
            change_reason=f"{change_type}: {reason}"[:255],
            created_at=datetime.utcnow()
        )
        s.add(ver_rec)

        # 2. تسجيل مجموعة التغيير (Corpus Changeset)
        changeset = CorpusChangeset(
            corpus_version=version_id,
            event_id=event_id,
            change_type=change_type,
            reference_id=reference_id,
            previous_reference_id=previous_reference_id,
            actor=actor,
            reason=reason,
            resulting_status=resulting_status,
            timestamp=datetime.utcnow()
        )
        s.add(changeset)

        # 3. تعليم الفهرس كـ stale
        mark_index_stale(corpus_version=version_id, session=s)

        logger.info(f"تم حجز إصدار قاعدة مراجع جديد: {version_id} (النوع: {change_type}، المرجع: {reference_id})")
        return version_id

    if session:
        v_id = _execute(session)
    else:
        with get_session() as s:
            v_id = _execute(s)

    if not session:
        try:
            audit_service.record_event(
                action="reference_corpus.version_created",
                category="reference",
                object_type="reference_corpus",
                object_id=v_id,
                success=True,
                metadata={
                    "change_type": change_type,
                    "reference_id": reference_id,
                    "actor": actor,
                    "reason": reason
                }
            )
        except Exception as e:
            logger.warning(f"تعذر توثيق حدث إصدار قاعدة المراجع في التدقيق: {e}")

    return v_id


def get_current_corpus_info() -> Dict[str, Any]:
    """استرجاع معلومات الإصدار الحالي لقاعدة المراجع."""
    with get_session() as session:
        latest_ver = (
            session.query(ReferenceCorpusVersion)
            .order_by(ReferenceCorpusVersion.id.desc())
            .first()
        )
        active_count = (
            session.query(Document)
            .filter(Document.current_status == STATUS_ACTIVE)
            .count()
        )
        idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
        index_state = idx_rec.state if idx_rec else 'stale'
        index_ver = idx_rec.index_corpus_version if idx_rec else ''

        if not latest_ver:
            # خط الأساس الأولي
            fp, _ = compute_deterministic_corpus_fingerprint(session=session)
            year = datetime.now().year
            seq_val = reference_service.get_next_sequence_value('reference_corpus', year)
            ver_id = f"REF-{year}-{seq_val:06d}"
            base_rec = ReferenceCorpusVersion(
                version_identifier=ver_id,
                fingerprint=fp,
                document_count=active_count,
                change_reason="initial_baseline",
                created_at=datetime.utcnow()
            )
            session.add(base_rec)
            return {
                'corpus_version': ver_id,
                'fingerprint': fp,
                'active_count': active_count,
                'index_state': index_state,
                'index_version': index_ver,
                'last_updated': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
            }

        return {
            'corpus_version': latest_ver.version_identifier,
            'fingerprint': latest_ver.fingerprint,
            'active_count': active_count,
            'index_state': index_state,
            'index_version': index_ver,
            'last_updated': latest_ver.created_at.strftime('%Y-%m-%d %H:%M:%S') if latest_ver.created_at else ''
        }


def add_reference_document(
    title: str,
    author: str = '',
    year: str = '',
    publisher: str = '',
    edition: str = '',
    document_type: str = 'paper',
    source_category: str = 'academic',
    category: str = 'عام',
    file_path: str = '',
    raw_text: str = '',
    original_filename: str = '',
    added_by: str = 'system',
    notes: str = '',
    ownership_note: str = ''
) -> dict:
    """
    إضافة مرجع جديد مع التحقق الصارم من عدم التكرار، وبناء الهوية المستقرة، وإصدار النسخة الذرية.
    """
    title = (title or '').strip()
    if not title:
        return {'success': False, 'error_code': ErrorCode.VALIDATION_ERROR, 'error': 'عنوان المرجع مطلوب'}

    # 1. فحص البصمة الرقمية للبيانات الثنائية (SHA-256)
    file_hash = ''
    size_bytes = 0
    if file_path and os.path.exists(file_path):
        file_hash, size_bytes = integrity_service.compute_stream_sha256(file_path)
    elif raw_text:
        b_text = raw_text.encode('utf-8')
        file_hash = hashlib.sha256(b_text).hexdigest()
        size_bytes = len(b_text)
    else:
        file_hash = None

    # 2. سياسة منع التكرار المعتمدة على الهاش التام للمراجع النشطة فقط
    if file_hash:
        with get_session() as session:
            existing = (
                session.query(Document)
                .filter(Document.file_hash == file_hash, Document.current_status == STATUS_ACTIVE)
                .first()
            )
            if existing:
                audit_service.record_event(
                    action="reference.duplicate_rejected",
                    category="reference",
                    object_type="reference_document",
                    object_id=str(existing.reference_id or existing.id),
                    user={'username': added_by},
                    success=False,
                    metadata={
                        "title": title,
                        "existing_ref_id": existing.reference_id,
                        "existing_title": existing.title,
                        "hash_prefix": file_hash[:16]
                    }
                )
                return {
                    'success': False,
                    'is_duplicate': True,
                    'error_code': ErrorCode.REFERENCE_DUPLICATE,
                    'existing_reference_id': existing.reference_id,
                    'existing_id': existing.id,
                    'existing_title': existing.title,
                    'error': f"هذا الملف موجود مسبقاً في قاعدة المراجع النشطة تحت عنوان: «{existing.title}» (المعرف: {existing.reference_id})"
                }

    # 3. استخراج الصفحات الفردية
    pages_data = []
    if file_path and os.path.exists(file_path):
        pages_data = extract_document_pages(file_path, enable_ocr=True)
        if not raw_text:
            raw_text = '\n\n'.join(p['text'] for p in pages_data if p['text'])
    elif raw_text:
        pages_data = [{'page_number': None, 'text': raw_text, 'is_ocr': False}]

    if not raw_text.strip():
        return {
            'success': False,
            'error_code': ErrorCode.FILE_EMPTY,
            'error': 'لم يتم العثور على نص صالح للاستخراج من هذا الملف'
        }

    # 4. التقطيع إلى فقرات
    segments_data = segment_pages(pages_data, min_words=4)

    # 5. تصنيف التخصص
    if not category or category == 'عام':
        category = categorize_text(raw_text)

    # 6. توليد الهوية المستقرة للمرجع
    reference_id = f"ref-{uuid.uuid4().hex[:12]}"

    # 7. الحفظ وإصدار النسخة التراكمية في معاملة ذرية موحدة
    try:
        with get_session() as session:
            # حجز إصدار قاعدة المراجع
            corpus_ver = allocate_corpus_version(
                change_type="add",
                reference_id=reference_id,
                actor=added_by,
                reason=f"إضافة مرجع جديد: {title[:50]}",
                resulting_status=STATUS_ACTIVE,
                session=session
            )

            doc = Document(
                reference_id=reference_id,
                title=title,
                author=author.strip() if author else '',
                year=year.strip() if year else '',
                publisher=publisher.strip() if publisher else '',
                edition=edition.strip() if edition else '',
                document_type=document_type.strip() if document_type else 'paper',
                source_category=source_category.strip() if source_category else 'academic',
                category=category.strip() if category else 'عام',
                file_path=file_path,
                original_filename=original_filename or (os.path.basename(file_path) if file_path else ''),
                size_bytes=size_bytes,
                file_hash=file_hash,
                current_status=STATUS_ACTIVE,
                added_by=added_by,
                notes=notes,
                ownership_note=ownership_note,
                active_from_version=corpus_ver,
                inactive_from_version=None,
                integrity_status='verified',
                last_integrity_check=datetime.utcnow()
            )
            session.add(doc)
            session.flush()

            # إضافة الصفحات
            if pages_data:
                for p in pages_data:
                    p_obj = DocumentPage(
                        document_id=doc.id,
                        page_number=p.get('page_number'),
                        raw_text=p.get('text', ''),
                        normalized_text=normalize_light(p.get('text', ''))
                    )
                    session.add(p_obj)

            # إضافة المقاطع
            if segments_data:
                for s in segments_data:
                    seg_obj = DocumentSegment(
                        document_id=doc.id,
                        page_number=getattr(s, 'page_number', None) if not isinstance(s, dict) else s.get('page_number'),
                        segment_number=getattr(s, 'segment_number', 1) if not isinstance(s, dict) else s.get('segment_number', 1),
                        raw_text=getattr(s, 'raw_text', '') if not isinstance(s, dict) else s.get('raw_text', ''),
                        normalized_text=getattr(s, 'normalized_light', '') if not isinstance(s, dict) else s.get('normalized_light', ''),
                        word_count=getattr(s, 'word_count', 0) if not isinstance(s, dict) else s.get('word_count', 0)
                    )
                    session.add(seg_obj)

            session.flush()
            doc_id = doc.id
            doc_title = doc.title
            doc_author = doc.author
            doc_category = doc.category
            session.commit()
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc) or "IntegrityError" in type(exc).__name__:
            if file_hash:
                with get_session() as s2:
                    existing = (
                        s2.query(Document)
                        .filter(Document.file_hash == file_hash, Document.current_status == STATUS_ACTIVE)
                        .first()
                    )
                    if existing:
                        return {
                            'success': False,
                            'is_duplicate': True,
                            'error_code': ErrorCode.REFERENCE_DUPLICATE,
                            'existing_reference_id': existing.reference_id,
                            'existing_id': existing.id,
                            'existing_title': existing.title,
                            'error': f"هذا الملف موجود مسبقاً في قاعدة المراجع النشطة تحت عنوان: «{existing.title}» (المعرف: {existing.reference_id})"
                        }
            return {
                'success': False,
                'is_duplicate': True,
                'error_code': ErrorCode.REFERENCE_DUPLICATE,
                'error': 'تعذر حفظ المرجع لوجود تكرار متزامن'
            }
        raise exc

    # توثيق في سجل التدقيق
    audit_service.record_event(
        action="reference.added",
        category="reference",
        object_type="reference_document",
        object_id=reference_id,
        user={'username': added_by},
        success=True,
        metadata={
            "title": title,
            "author": author,
            "corpus_version": corpus_ver,
            "pages_count": len(pages_data),
            "segments_count": len(segments_data)
        }
    )

    return {
        'success': True,
        'id': doc_id,
        'reference_id': reference_id,
        'title': doc_title,
        'author': doc_author,
        'category': doc_category,
        'corpus_version': corpus_ver,
        'pages_count': len(pages_data),
        'segments_count': len(segments_data),
        'current_status': STATUS_ACTIVE,
        'status_label_ar': STATUS_LABELS_AR[STATUS_ACTIVE]
    }


def retire_reference_document(
    reference_id_or_id: Any,
    actor: str = 'system',
    reason: str = ''
) -> dict:
    """
    إيقاف/استبعاد مرجع من الفحوصات المستقبلية مع الحفاظ التام على ملفه ووجوده التاريخي.
    """
    with get_session() as session:
        doc = _find_document(session, reference_id_or_id)
        if not doc:
            return {'success': False, 'error_code': ErrorCode.REFERENCE_NOT_FOUND, 'error': 'المرجع غير موجود'}

        if doc.current_status == STATUS_RETIRED:
            return {
                'success': False,
                'error_code': ErrorCode.REFERENCE_ALREADY_RETIRED,
                'error': 'المرجع موقوف بالفعل'
            }

        # حجز إصدار جديد وترقية قاعدة المراجع
        corpus_ver = allocate_corpus_version(
            change_type="retire",
            reference_id=doc.reference_id,
            actor=actor,
            reason=reason or "إيقاف مرجع عن الفحص",
            resulting_status=STATUS_RETIRED,
            session=session
        )

        doc.current_status = STATUS_RETIRED
        doc.inactive_from_version = corpus_ver
        doc_ref_id = doc.reference_id
        doc_title = doc.title
        session.commit()

    audit_service.record_event(
        action="reference.retired",
        category="reference",
        object_type="reference_document",
        object_id=doc_ref_id,
        user={'username': actor},
        success=True,
        metadata={
            "title": doc_title,
            "corpus_version": corpus_ver,
            "reason": reason
        }
    )

    return {
        'success': True,
        'reference_id': doc_ref_id,
        'corpus_version': corpus_ver,
        'current_status': STATUS_RETIRED,
        'status_label_ar': STATUS_LABELS_AR[STATUS_RETIRED]
    }


def supersede_reference_document(
    old_reference_id_or_id: Any,
    new_file_path: str = '',
    new_raw_text: str = '',
    new_title: str = '',
    new_author: str = '',
    new_year: str = '',
    new_publisher: str = '',
    new_edition: str = '',
    original_filename: str = '',
    actor: str = 'system',
    reason: str = ''
) -> dict:
    """
    استبدال مرجع قديم بإصدار أحدث (Versioned Supersession):
    - ينشئ هوية مرجعية جديدة بالكامل للملف الجديد (supersedes_reference_id = old_ref).
    - يغير حالة المرجع القديم إلى superseded مع ربطه بالإصدار الجديد.
    - يحافظ على ملف المرجع القديم وأدلته التاريخية دون أي حذف.
    - يصدر نسخة تراكمية موحدة لقاعدة المراجع.
    """
    with get_session() as session:
        old_doc = _find_document(session, old_reference_id_or_id)
        if not old_doc:
            return {'success': False, 'error_code': ErrorCode.REFERENCE_NOT_FOUND, 'error': 'المرجع السابق غير موجود'}

        if old_doc.current_status in (STATUS_SUPERSEDED, STATUS_RETIRED):
            return {
                'success': False,
                'error_code': ErrorCode.REFERENCE_SUPERSESSION_CONFLICT,
                'error': f'لا يمكن استبدال مرجع بحالة {old_doc.current_status}'
            }

        title = (new_title or old_doc.title).strip()
        author = (new_author or old_doc.author).strip()
        year = (new_year or old_doc.year).strip()
        publisher = (new_publisher or old_doc.publisher).strip()
        edition = (new_edition or old_doc.edition).strip()

        # 1. حساب الهاش الجديد
        new_hash = ''
        new_size = 0
        if new_file_path and os.path.exists(new_file_path):
            new_hash, new_size = integrity_service.compute_stream_sha256(new_file_path)
        elif new_raw_text:
            b_text = new_raw_text.encode('utf-8')
            new_hash = hashlib.sha256(b_text).hexdigest()
            new_size = len(b_text)

        # منع التكرار مع ملفات أخرى غير الملف المستبدل
        if new_hash:
            conflict = (
                session.query(Document)
                .filter(
                    Document.file_hash == new_hash,
                    Document.current_status == STATUS_ACTIVE,
                    Document.id != old_doc.id
                )
                .first()
            )
            if conflict:
                return {
                    'success': False,
                    'error_code': ErrorCode.REFERENCE_DUPLICATE,
                    'error': f"الملف الجديد مكرر مع مرجع نشط آخر: «{conflict.title}»"
                }

        # 2. استخراج الصفحات والفقرات
        pages_data = []
        if new_file_path and os.path.exists(new_file_path):
            pages_data = extract_document_pages(new_file_path, enable_ocr=True)
            if not new_raw_text:
                new_raw_text = '\n\n'.join(p['text'] for p in pages_data if p['text'])
        elif new_raw_text:
            pages_data = [{'page_number': None, 'text': new_raw_text, 'is_ocr': False}]

        if not new_raw_text.strip():
            return {
                'success': False,
                'error_code': ErrorCode.FILE_EMPTY,
                'error': 'لم يتم العثور على نص صالح للاستخراج من الملف المستبدل'
            }

        segments_data = segment_pages(pages_data, min_words=4)
        category = old_doc.category or categorize_text(new_raw_text)

        # 3. الهوية الجديدة
        new_reference_id = f"ref-{uuid.uuid4().hex[:12]}"

        # 4. ترقية النسخة الذرية
        corpus_ver = allocate_corpus_version(
            change_type="supersede",
            reference_id=new_reference_id,
            previous_reference_id=old_doc.reference_id,
            actor=actor,
            reason=reason or f"استبدال المرجع {old_doc.reference_id}",
            resulting_status=STATUS_ACTIVE,
            session=session
        )

        # 5. تحديث المرجع القديم
        old_doc.current_status = STATUS_SUPERSEDED
        old_doc.inactive_from_version = corpus_ver
        old_doc.superseded_by_reference_id = new_reference_id

        # 6. إنشاء المرجع الجديد
        new_doc = Document(
            reference_id=new_reference_id,
            title=title,
            author=author,
            year=year,
            publisher=publisher,
            edition=edition,
            document_type=old_doc.document_type,
            source_category=old_doc.source_category,
            category=category,
            file_path=new_file_path,
            original_filename=original_filename or (os.path.basename(new_file_path) if new_file_path else ''),
            size_bytes=new_size,
            file_hash=new_hash,
            current_status=STATUS_ACTIVE,
            added_by=actor,
            notes=f"مستبدل عن: {old_doc.reference_id}. {old_doc.notes or ''}".strip(),
            ownership_note=old_doc.ownership_note,
            supersedes_reference_id=old_doc.reference_id,
            superseded_by_reference_id=None,
            active_from_version=corpus_ver,
            inactive_from_version=None,
            integrity_status='verified',
            last_integrity_check=datetime.utcnow()
        )
        session.add(new_doc)
        session.flush()

        for p in pages_data:
            p_obj = DocumentPage(
                document_id=new_doc.id,
                page_number=p.get('page_number'),
                raw_text=p.get('text', ''),
                normalized_text=normalize_light(p.get('text', ''))
            )
            session.add(p_obj)

        for s in segments_data:
            seg_obj = DocumentSegment(
                document_id=new_doc.id,
                page_number=getattr(s, 'page_number', None) if not isinstance(s, dict) else s.get('page_number'),
                segment_number=getattr(s, 'segment_number', 1) if not isinstance(s, dict) else s.get('segment_number', 1),
                raw_text=getattr(s, 'raw_text', '') if not isinstance(s, dict) else s.get('raw_text', ''),
                normalized_text=getattr(s, 'normalized_light', '') if not isinstance(s, dict) else s.get('normalized_light', ''),
                word_count=getattr(s, 'word_count', 0) if not isinstance(s, dict) else s.get('word_count', 0)
            )
        session.flush()
        old_ref_id = old_doc.reference_id
        new_ref_id = new_doc.reference_id
        new_doc_title = new_doc.title
        session.commit()

    audit_service.record_event(
        action="reference.superseded",
        category="reference",
        object_type="reference_document",
        object_id=new_ref_id,
        user={'username': actor},
        success=True,
        metadata={
            "old_reference_id": old_ref_id,
            "new_reference_id": new_ref_id,
            "corpus_version": corpus_ver,
            "reason": reason
        }
    )

    return {
        'success': True,
        'old_reference_id': old_ref_id,
        'new_reference_id': new_ref_id,
        'corpus_version': corpus_ver,
        'title': new_doc_title,
        'current_status': STATUS_ACTIVE,
        'status_label_ar': STATUS_LABELS_AR[STATUS_ACTIVE]
    }


def reactivate_reference_document(
    reference_id_or_id: Any,
    actor: str = 'system',
    reason: str = ''
) -> dict:
    """
    إعادة تفعيل مرجع موقوف (reactivate) بعد التأكد من سلامة ملفه الفيزيائي.
    """
    with get_session() as session:
        doc = _find_document(session, reference_id_or_id)
        if not doc:
            return {'success': False, 'error_code': ErrorCode.REFERENCE_NOT_FOUND, 'error': 'المرجع غير موجود'}

        if doc.current_status == STATUS_ACTIVE:
            return {'success': False, 'error': 'المرجع نشط بالفعل'}

        # فحص سلامة الملف الفيزيائي أولاً
        if doc.file_path:
            if not os.path.exists(doc.file_path):
                return {
                    'success': False,
                    'error_code': ErrorCode.REFERENCE_INTEGRITY_FAILED,
                    'error': 'تعذر إعادة التفعيل: ملف المرجع غير موجود على القرص'
                }
            f_hash, f_size = integrity_service.compute_stream_sha256(doc.file_path)
            if doc.file_hash and f_hash != doc.file_hash:
                return {
                    'success': False,
                    'error_code': ErrorCode.REFERENCE_INTEGRITY_FAILED,
                    'error': 'تعذر إعادة التفعيل: بصمة الملف الحالية لا تطابق البصمة المعتمدة'
                }

        # حجز إصدار جديد
        corpus_ver = allocate_corpus_version(
            change_type="reactivate",
            reference_id=doc.reference_id,
            actor=actor,
            reason=reason or "إعادة تفعيل المرجع",
            resulting_status=STATUS_ACTIVE,
            session=session
        )

        doc.current_status = STATUS_ACTIVE
        doc.inactive_from_version = None
        doc.active_from_version = corpus_ver
        doc.integrity_status = 'verified'
        doc.last_integrity_check = datetime.utcnow()
        doc_ref_id = doc.reference_id
        doc_title = doc.title
        session.commit()

    audit_service.record_event(
        action="reference.reactivated",
        category="reference",
        object_type="reference_document",
        object_id=doc_ref_id,
        user={'username': actor},
        success=True,
        metadata={
            "title": doc_title,
            "corpus_version": corpus_ver,
            "reason": reason
        }
    )

    return {
        'success': True,
        'reference_id': doc_ref_id,
        'corpus_version': corpus_ver,
        'current_status': STATUS_ACTIVE,
        'status_label_ar': STATUS_LABELS_AR[STATUS_ACTIVE]
    }


def verify_reference_integrity(reference_id_or_id: Any, mark_invalid_on_failure: bool = True) -> dict:
    """
    التحقق الصارم من نزاهة ملف المرجع ووجوده ومطابقة حجمه والهاش الرقمي SHA-256.
    """
    with get_session() as session:
        doc = _find_document(session, reference_id_or_id)
        if not doc:
            return {'success': False, 'error_code': ErrorCode.REFERENCE_NOT_FOUND, 'error': 'المرجع غير موجود'}

        if not doc.file_path:
            # مرجع نصي بدون ملف فيزيائي
            return {
                'success': True,
                'reference_id': doc.reference_id,
                'integrity_status': 'verified',
                'is_intact': True,
                'message': 'مرجع نصي خالص سليم'
            }

        if not os.path.exists(doc.file_path):
            doc.integrity_status = 'missing'
            doc.last_integrity_check = datetime.utcnow()
            if mark_invalid_on_failure and doc.current_status == STATUS_ACTIVE:
                corpus_ver = allocate_corpus_version(
                    change_type="invalidate",
                    reference_id=doc.reference_id,
                    actor="system",
                    reason="فقدان الملف الفيزيائي على القرص",
                    resulting_status=STATUS_INVALID,
                    session=session
                )
                doc.current_status = STATUS_INVALID
                doc.inactive_from_version = corpus_ver
            session.commit()
            return {
                'success': False,
                'reference_id': doc.reference_id,
                'integrity_status': 'missing',
                'is_intact': False,
                'error_code': ErrorCode.REFERENCE_INTEGRITY_FAILED,
                'error': 'ملف المرجع مفقود من مسار التخزين'
            }

        cur_hash, cur_size = integrity_service.compute_stream_sha256(doc.file_path)
        hash_matches = bool(doc.file_hash and cur_hash == doc.file_hash)
        size_matches = bool(not doc.size_bytes or cur_size == doc.size_bytes)

        if not (hash_matches and size_matches):
            doc.integrity_status = 'corrupted'
            doc.last_integrity_check = datetime.utcnow()
            if mark_invalid_on_failure and doc.current_status == STATUS_ACTIVE:
                corpus_ver = allocate_corpus_version(
                    change_type="invalidate",
                    reference_id=doc.reference_id,
                    actor="system",
                    reason="عدم تطابق البصمة الرقمية أو الحجم للملف",
                    resulting_status=STATUS_INVALID,
                    session=session
                )
                doc.current_status = STATUS_INVALID
                doc.inactive_from_version = corpus_ver
            session.commit()
            return {
                'success': False,
                'reference_id': doc.reference_id,
                'integrity_status': 'corrupted',
                'is_intact': False,
                'error_code': ErrorCode.REFERENCE_INTEGRITY_FAILED,
                'error': 'بصمة الملف الفيزيائي لا تطابق البصمة المسجلة'
            }

        doc.integrity_status = 'verified'
        doc.last_integrity_check = datetime.utcnow()
        session.commit()

        return {
            'success': True,
            'reference_id': doc.reference_id,
            'integrity_status': 'verified',
            'is_intact': True,
            'size_bytes': cur_size,
            'file_hash': cur_hash
        }


def edit_reference_metadata(
    reference_id_or_id: Any,
    updates: dict,
    actor: str = 'system',
    reason: str = ''
) -> dict:
    """
    تعديل البيانات الوصفية للمرجع وتوثيق الفروقات في سجل التعديلات (Metadata Revision History).
    - سياسة التعديل الوصفي: لا تغير البصمة الثنائية لقاعدة المراجع (لأن نصوص الملفات لم تتغير)،
      وتحفظ لقطات التقارير المعتمدة السابقة دون أي مساس بنسبتها.
    """
    with get_session() as session:
        doc = _find_document(session, reference_id_or_id)
        if not doc:
            return {'success': False, 'error_code': ErrorCode.REFERENCE_NOT_FOUND, 'error': 'المرجع غير موجود'}

        allowed_fields = [
            'title', 'author', 'year', 'publisher', 'edition',
            'document_type', 'source_category', 'category', 'notes', 'ownership_note'
        ]

        changed_fields = []
        for field in allowed_fields:
            if field in updates and updates[field] is not None:
                new_val = str(updates[field]).strip()
                old_val = str(getattr(doc, field) or '')
                if new_val != old_val:
                    # توثيق في سجل التاريخ
                    hist = ReferenceMetadataHistory(
                        document_id=doc.id,
                        reference_id=doc.reference_id,
                        field_name=field,
                        old_value=old_val,
                        new_value=new_val,
                        changed_by=actor,
                        reason=reason,
                        changed_at=datetime.utcnow()
                    )
                    session.add(hist)
                    setattr(doc, field, new_val)
                    changed_fields.append(field)

        doc_ref_id = doc.reference_id
        session.commit()

    if changed_fields:
        audit_service.record_event(
            action="reference.metadata_changed",
            category="reference",
            object_type="reference_document",
            object_id=doc_ref_id,
            user={'username': actor},
            success=True,
            metadata={
                "changed_fields": changed_fields,
                "reason": reason
            }
        )

    return {
        'success': True,
        'reference_id': doc_ref_id,
        'changed_fields': changed_fields
    }


def reconstruct_historical_corpus_membership(target_corpus_version: str) -> List[Dict[str, Any]]:
    """
    استنساخ عضوية قاعدة المراجع النشطة في لحظة إصدار تاريخي محدد (Historical Reconstruction).
    تعتمد على سجل التغييرات المتسلسل (Corpus Changesets) لمعرفة الحالة المؤكدة لكل مرجع عند ذلك الإصدار بدقة عبر كافة دورات التفعيل والإيقاف المتكررة.
    """
    with get_session() as session:
        # 1. استرجاع حركات التغيير المسجلة حتى الإصدار المستهدف
        changesets = (
            session.query(CorpusChangeset)
            .filter(CorpusChangeset.corpus_version <= target_corpus_version)
            .order_by(CorpusChangeset.id.asc())
            .all()
        )

        if changesets:
            ref_status_map = {}
            for cs in changesets:
                if cs.reference_id:
                    ref_status_map[cs.reference_id] = cs.resulting_status

            active_ref_ids = [ref_id for ref_id, status in ref_status_map.items() if status == STATUS_ACTIVE]

            if active_ref_ids:
                docs = (
                    session.query(Document)
                    .filter(Document.reference_id.in_(active_ref_ids))
                    .order_by(Document.reference_id.asc())
                    .all()
                )
                return [
                    {
                        'id': d.id,
                        'reference_id': d.reference_id,
                        'title': d.title,
                        'author': d.author,
                        'file_hash': d.file_hash,
                        'active_from_version': d.active_from_version,
                        'inactive_from_version': d.inactive_from_version
                    }
                    for d in docs
                ]
            return []

        # 2. بديل متوافق للبيانات السابقة عبر حدود الإصدارات (active_from_version / inactive_from_version)
        query = (
            session.query(Document)
            .filter(Document.active_from_version <= target_corpus_version)
            .filter(
                or_(
                    Document.inactive_from_version.is_(None),
                    Document.inactive_from_version == '',
                    Document.inactive_from_version > target_corpus_version
                )
            )
            .order_by(Document.reference_id.asc())
        )
        docs = query.all()

        return [
            {
                'id': d.id,
                'reference_id': d.reference_id,
                'title': d.title,
                'author': d.author,
                'file_hash': d.file_hash,
                'active_from_version': d.active_from_version,
                'inactive_from_version': d.inactive_from_version
            }
            for d in docs
        ]


def get_reference_history(reference_id_or_id: Any) -> Dict[str, Any]:
    """استرجاع السجل التاريخي الكامل لمرجع محدد (التعديلات، الحركات، وسلسلة الإصدارات)."""
    with get_session() as session:
        doc = _find_document(session, reference_id_or_id)
        if not doc:
            return {'success': False, 'error_code': ErrorCode.REFERENCE_NOT_FOUND, 'error': 'المرجع غير موجود'}

        # 1. سجل التعديلات الوصفية
        meta_history = (
            session.query(ReferenceMetadataHistory)
            .filter(ReferenceMetadataHistory.reference_id == doc.reference_id)
            .order_by(ReferenceMetadataHistory.changed_at.desc())
            .all()
        )

        # 2. سجل التغييرات في قاعدة المراجع
        changesets = (
            session.query(CorpusChangeset)
            .filter(
                or_(
                    CorpusChangeset.reference_id == doc.reference_id,
                    CorpusChangeset.previous_reference_id == doc.reference_id
                )
            )
            .order_by(CorpusChangeset.timestamp.desc())
            .all()
        )

        return {
            'success': True,
            'reference_id': doc.reference_id,
            'title': doc.title,
            'author': doc.author,
            'current_status': doc.current_status,
            'status_label_ar': STATUS_LABELS_AR.get(doc.current_status, doc.current_status),
            'active_from_version': doc.active_from_version,
            'inactive_from_version': doc.inactive_from_version,
            'supersedes_reference_id': doc.supersedes_reference_id,
            'superseded_by_reference_id': doc.superseded_by_reference_id,
            'integrity_status': doc.integrity_status,
            'last_integrity_check': doc.last_integrity_check.strftime('%Y-%m-%d %H:%M:%S') if doc.last_integrity_check else None,
            'metadata_history': [
                {
                    'field_name': h.field_name,
                    'old_value': h.old_value,
                    'new_value': h.new_value,
                    'changed_by': h.changed_by,
                    'reason': h.reason,
                    'changed_at': h.changed_at.strftime('%Y-%m-%d %H:%M:%S') if h.changed_at else ''
                }
                for h in meta_history
            ],
            'changesets': [
                {
                    'corpus_version': c.corpus_version,
                    'change_type': c.change_type,
                    'reference_id': c.reference_id,
                    'previous_reference_id': c.previous_reference_id,
                    'actor': c.actor,
                    'reason': c.reason,
                    'resulting_status': c.resulting_status,
                    'timestamp': c.timestamp.strftime('%Y-%m-%d %H:%M:%S') if c.timestamp else ''
                }
                for c in changesets
            ]
        }


def _find_document(session, ref_id_or_id: Any) -> Optional[Document]:
    """دالة مساعدة للبحث عن المرجع إما بالمعرف المستقر reference_id أو المعرف الرقمي id."""
    if isinstance(ref_id_or_id, int) or (isinstance(ref_id_or_id, str) and ref_id_or_id.isdigit()):
        doc = session.query(Document).filter(Document.id == int(ref_id_or_id)).first()
        if doc:
            return doc
    return session.query(Document).filter(Document.reference_id == str(ref_id_or_id)).first()
