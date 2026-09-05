# -*- coding: utf-8 -*-
"""
مستودع بيانات الأبحاث والوثائق المرجعية (Document Repository):
- استعلامات وحفظ الأبحاث على مستوى الصفحات والفقرات.
- كشف ومنع تكرار الملفات عبر SHA-256 File Hash.
- عمليات الفهرسة والتصفح والتعديل والحذف.
"""

from typing import Optional
from sqlalchemy import or_, func

from app.repositories.base_repo import get_session
from app.models.schema import Document, DocumentPage, DocumentSegment
from plagiarism_detector.preprocessing.normalizer import normalize_light, normalize_aggressive


def get_document_by_hash(file_hash: str) -> Optional[dict]:
    """البحث عن بحث سابق بنفس البصمة الرقمية SHA-256 لمنع التكرار."""
    if not file_hash:
        return None
    with get_session() as session:
        doc = session.query(Document).filter(Document.file_hash == file_hash).first()
        if doc:
            return {
                'id': doc.id,
                'title': doc.title,
                'author': doc.author,
                'category': doc.category,
                'file_path': doc.file_path,
                'created_at': doc.created_at.isoformat() if doc.created_at else ''
            }
    return None


def get_document_by_title(title: str) -> Optional[dict]:
    """فحص وجود بحث بنفس العنوان."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.title == title.strip()).first()
        if doc:
            return {'id': doc.id, 'title': doc.title, 'author': doc.author}
    return None


def add_document(
    title: str,
    author: str = '',
    year: str = '',
    category: str = 'عام',
    file_path: str = '',
    file_hash: str = '',
    pages_data: list[dict] = None,
    segments_data: list = None
) -> dict:
    """
    إضافة بحث جديد إلى قاعدة البيانات مع صفحاته وفقراته الكاملة.
    """
    with get_session() as session:
        doc = Document(
            title=title.strip(),
            author=author.strip() if author else '',
            year=year.strip() if year else '',
            category=category.strip() if category else 'عام',
            file_path=file_path,
            file_hash=file_hash
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

        # إضافة المقاطع / الفقرات
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

        session.commit()

        # تحديث وتتبع إصدار قاعدة المراجع
        try:
            from app.services import snapshot_service
            snapshot_service.get_current_reference_corpus_info()
        except Exception:
            pass

        return {
            'id': doc.id,
            'title': doc.title,
            'author': doc.author,
            'category': doc.category,
            'file_path': doc.file_path,
            'file_hash': doc.file_hash
        }


def get_all_documents(
    page: int = 1,
    per_page: int = 25,
    query: str = '',
    status: Optional[str] = None,
    publication_year: Optional[str] = None,
    file_hash: Optional[str] = None,
    reference_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort_field: str = 'id',
    order_direction: str = 'desc'
) -> dict:
    """استرجاع قائمة الأبحاث المرجعية مع ترقيم الصفحات والبحث النصي وتصفية الحالات المؤسسية."""
    from datetime import datetime
    from app.utils.search_normalizer import normalize_search_query
    from app.services.corpus_governance_service import STATUS_LABELS_AR

    with get_session() as session:
        q = session.query(Document)

        if status:
            q = q.filter(Document.current_status == status.strip())
        if publication_year:
            q = q.filter(Document.year == publication_year.strip())
        if file_hash:
            q = q.filter(Document.file_hash == file_hash.strip())
        if reference_id:
            q = q.filter(Document.reference_id == reference_id.strip())

        if date_from:
            try:
                dt_from = datetime.strptime(date_from[:10], '%Y-%m-%d')
                q = q.filter(Document.created_at >= dt_from)
            except ValueError:
                pass
        if date_to:
            try:
                dt_to = datetime.strptime(date_to[:10], '%Y-%m-%d')
                dt_to = dt_to.replace(hour=23, minute=59, second=59)
                q = q.filter(Document.created_at <= dt_to)
            except ValueError:
                pass

        if query:
            clean_q = normalize_search_query(query)
            q_norm = f"%{clean_q}%"
            q = q.filter(
                or_(
                    Document.title.ilike(q_norm),
                    Document.author.ilike(q_norm),
                    Document.category.ilike(q_norm),
                    Document.reference_id.ilike(q_norm)
                )
            )

        total = q.order_by(None).count()

        sort_col = Document.id
        if sort_field == 'title':
            sort_col = Document.title
        elif sort_field == 'author':
            sort_col = Document.author
        elif sort_field == 'created_at':
            sort_col = Document.created_at
        elif sort_field == 'reference_id':
            sort_col = Document.reference_id

        if order_direction == 'asc':
            q = q.order_by(sort_col.asc())
        else:
            q = q.order_by(sort_col.desc())

        docs = q.offset((page - 1) * per_page).limit(per_page).all()

        results = []
        for d in docs:
            results.append({
                'id': d.id,
                'reference_id': d.reference_id or f"doc-{d.id}",
                'title': d.title,
                'author': d.author or 'غير محدد',
                'year': d.year or '',
                'publisher': d.publisher or '',
                'edition': d.edition or '',
                'document_type': d.document_type or 'paper',
                'source_category': d.source_category or 'academic',
                'category': d.category or 'عام',
                'file_path': d.file_path,
                'file_hash': d.file_hash or '',
                'size_bytes': d.size_bytes or 0,
                'current_status': d.current_status or 'active',
                'status_label_ar': STATUS_LABELS_AR.get(d.current_status, 'نشط'),
                'active_from_version': d.active_from_version or '',
                'inactive_from_version': d.inactive_from_version,
                'supersedes_reference_id': d.supersedes_reference_id,
                'superseded_by_reference_id': d.superseded_by_reference_id,
                'integrity_status': d.integrity_status or 'verified',
                'added_at': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else ''
            })

        total_pages = max(1, (total + per_page - 1) // per_page)
        return {
            'items': results,
            'papers': results,
            'total_items': total,
            'total': total,
            'page': page,
            'page_size': per_page,
            'per_page': per_page,
            'total_pages': total_pages
        }


def get_document_count(status: Optional[str] = None) -> int:
    """إرجاع إجمالي عدد الأبحاث المرجعية (أو الأبحاث النشطة فقط)."""
    with get_session() as session:
        q = session.query(Document)
        if status:
            q = q.filter(Document.current_status == status)
        return q.count()


def delete_document(doc_id: int) -> bool:
    """
    حذف أو إيقاف المرجع وفق سياسة الحوكمة المؤسسية.
    إذا كان المرجع نشطاً أو يمتلك تاريخاً، يتم تحويله إلى حالة موقوف (retired) بدلاً من الحذف الفيزيائي.
    """
    from app.services import corpus_governance_service
    res = corpus_governance_service.retire_reference_document(
        reference_id_or_id=doc_id,
        actor="system",
        reason="حذف عبر مسار الإدارة"
    )
    return res.get('success', False)


def update_document(doc_id: int, title: str = None, author: str = None, category: str = None, year: str = None) -> bool:
    """تعديل بيانات بحث مرجعي مع توثيق التعديل في سجل التاريخ."""
    from app.services import corpus_governance_service
    updates = {}
    if title is not None:
        updates['title'] = title
    if author is not None:
        updates['author'] = author
    if category is not None:
        updates['category'] = category
    if year is not None:
        updates['year'] = year

    res = corpus_governance_service.edit_reference_metadata(
        reference_id_or_id=doc_id,
        updates=updates,
        actor="system",
        reason="تحديث بيانات عبر واجهة المراجع"
    )
    return res.get('success', False)


def get_all_segments_for_index() -> list[dict]:
    """
    استرجاع كافة مقاطع الأبحاث المرجعية النشطة فقط (current_status == 'active') لبناء فهرس الاسترجاع.
    يشمل: معرف البحث، المعرف المستقر، رقم الصفحة الحقيقي، النص المطبَّع، والنص الأصلي.
    """
    with get_session() as session:
        rows = (
            session.query(
                DocumentSegment.id,
                DocumentSegment.document_id,
                DocumentSegment.page_number,
                DocumentSegment.segment_number,
                DocumentSegment.raw_text,
                DocumentSegment.normalized_text,
                Document.title,
                Document.author,
                Document.reference_id
            )
            .join(Document, Document.id == DocumentSegment.document_id)
            .filter(Document.current_status == 'active')
            .all()
        )

        segments = []
        for r in rows:
            segments.append({
                'seg_id': r[0],
                'doc_id': r[1],
                'page_number': r[2],  # رقم الصفحة المصدرية الحقيقية (أو None)
                'segment_number': r[3],
                'raw_text': r[4],
                'normalized_text': r[5] or normalize_light(r[4]),
                'title': r[6],
                'author': r[7] or '',
                'reference_id': r[8] or f"doc-{r[1]}"
            })
        return segments


def clear_all_documents():
    """حذف كافة المراجع."""
    with get_session() as session:
        session.query(DocumentSegment).delete()
        session.query(DocumentPage).delete()
        session.query(Document).delete()
