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
        return {
            'id': doc.id,
            'title': doc.title,
            'author': doc.author,
            'category': doc.category,
            'file_path': doc.file_path,
            'file_hash': doc.file_hash
        }


def get_all_documents(page: int = 1, per_page: int = 10, query: str = '') -> dict:
    """استرجاع قائمة الأبحاث مع ترقيم الصفحات والبحث النصي."""
    with get_session() as session:
        q = session.query(Document)
        if query:
            q_norm = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Document.title.ilike(q_norm),
                    Document.author.ilike(q_norm),
                    Document.category.ilike(q_norm)
                )
            )

        total = q.count()
        docs = q.order_by(Document.id.desc()).offset((page - 1) * per_page).limit(per_page).all()

        results = []
        for d in docs:
            results.append({
                'id': d.id,
                'title': d.title,
                'author': d.author or 'غير محدد',
                'category': d.category or 'عام',
                'file_path': d.file_path,
                'added_at': d.created_at.strftime('%Y-%m-%d %H:%M') if d.created_at else ''
            })

        return {
            'papers': results,
            'total': total,
            'page': page,
            'total_pages': max(1, (total + per_page - 1) // per_page)
        }


def get_document_count() -> int:
    """إرجاع إجمالي عدد الأبحاث المرجعية."""
    with get_session() as session:
        return session.query(Document).count()


def delete_document(doc_id: int) -> bool:
    """حذف بحث وصفحاته وفقراته من قاعدة البيانات."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if doc:
            session.delete(doc)
            return True
    return False


def update_document(doc_id: int, title: str = None, author: str = None, category: str = None, year: str = None) -> bool:
    """تعديل بيانات بحث مرجعي."""
    with get_session() as session:
        doc = session.query(Document).filter(Document.id == doc_id).first()
        if doc:
            if title is not None:
                doc.title = title.strip()
            if author is not None:
                doc.author = author.strip()
            if category is not None:
                doc.category = category.strip()
            if year is not None:
                doc.year = year.strip()
            return True
    return False


def get_all_segments_for_index() -> list[dict]:
    """
    استرجاع كافة مقاطع الأبحاث المخزنة لبناء فهرس الكشف السريع.
    يشمل: معرف البحث، رقم الصفحة الحقيقي، النص المطبَّع، والنص الأصلي.
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
                Document.author
            )
            .join(Document, Document.id == DocumentSegment.document_id)
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
                'author': r[7] or ''
            })
        return segments


def clear_all_documents():
    """حذف كافة المراجع."""
    with get_session() as session:
        session.query(DocumentSegment).delete()
        session.query(DocumentPage).delete()
        session.query(Document).delete()
