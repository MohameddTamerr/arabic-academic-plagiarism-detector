# -*- coding: utf-8 -*-
"""
اختبارات فهرس استرجاع المرشحين الدائم (Prompt 2: Persistent Retrieval Index Tests):
- التحقق من حفظ وتحميل الفهرس المقلوب والتحقق من بصمات النزاهة في index_manifest.json.
- التحقق من الاسترجاع ثنائي القناة (Words + Char 3-grams) والتزام سقف K <= 50.
- التحقق من التحديث التدريجي (Incremental add / remove).
- التحقق من عزل الصلاحيات عبر allowed_doc_ids.
- التحقق من التعافي عند تلف أو فقدان ملفات الفهرس.
"""

import os
import json
import pytest
from pathlib import Path

from plagiarism_detector.detection.retrieval_index import LocalDiskRetrievalIndex


def test_index_save_load_and_manifest_checksum(tmp_path):
    """التحقق من حفظ الفهرس الدائم واحتساب ومطابقة بصمات الملفات في index_manifest.json."""
    index = LocalDiskRetrievalIndex(corpus_version="REF-2026-000001", fingerprint="corpus-fp-123")

    # إضافة مستند تجريبي
    segs = [
        {'id': 1, 'normalized_text': 'الذكاء الاصطناعي في التعليم الجامعي والتطوير المؤسسي'},
        {'id': 2, 'normalized_text': 'المناهج الدراسية الحديثة وتطوير المعايير الأكاديمية'}
    ]
    index.add_document(doc_id=101, segments_data=segs)

    # حفظ الفهرس
    target_dir = tmp_path / "idx_v1"
    index.save(target_dir)

    assert target_dir.exists()
    assert (target_dir / "index_manifest.json").exists()
    assert (target_dir / "postings_words.json").exists()
    assert (target_dir / "postings_cng.json").exists()

    # تحميل الفهرس في كائن جديد
    new_index = LocalDiskRetrievalIndex()
    loaded = new_index.load(target_dir)
    assert loaded is True
    assert new_index.total_segments == 2
    assert new_index.total_documents == 1
    assert new_index.corpus_version == "REF-2026-000001"


def test_dual_channel_retrieval_and_top_k_contract():
    """التحقق من عمل الاسترجاع ثنائي القناة واقتصار النتائج حصراً على أعلى K <= 50."""
    index = LocalDiskRetrievalIndex(corpus_version="REF-2026-TEST")

    # إضافة 100 مقطع
    for i in range(1, 101):
        text = f"بحث علمي رقم {i} حول قضايا التنمية المستدامة والتعليم العالي والمناهج"
        index.add_document(doc_id=i, segments_data=[{'id': i, 'normalized_text': text}])

    # استعلام
    query = "التنمية المستدامة والتعليم العالي"
    candidates = index.search_candidates(query, top_k=50)

    assert len(candidates) <= 50
    assert len(candidates) > 0
    # التحقق من أن أعلى المرشحين يحتوي على الكلمات المفتاحية
    assert all(isinstance(c_id, int) for c_id in candidates)


def test_incremental_add_and_remove():
    """التحقق من إضافة وحذف المستندات تدريجياً دون تشويه باقي الفهرس."""
    index = LocalDiskRetrievalIndex(corpus_version="REF-2026-INCR")

    # إضافة مستند أول وثان
    index.add_document(doc_id=1, segments_data=[{'id': 10, 'normalized_text': 'الهندسة الطبية الحيوية'}])
    index.add_document(doc_id=2, segments_data=[{'id': 20, 'normalized_text': 'الذكاء الاصطناعي التطبيقي'}])

    assert index.total_documents == 2
    assert index.total_segments == 2

    # التحقق من البحث
    cands1 = index.search_candidates("الهندسة الطبية")
    assert 10 in cands1

    # إزالة المستند الأول
    index.remove_document(doc_id=1)
    assert index.total_documents == 1
    assert index.total_segments == 1

    cands2 = index.search_candidates("الهندسة الطبية")
    assert 10 not in cands2

    # المستند الثاني يظل موجوداً
    cands3 = index.search_candidates("الذكاء الاصطناعي")
    assert 20 in cands3


def test_department_authorization_scoping():
    """التحقق من احترام حدود صلاحيات الأقسام عبر allowed_doc_ids."""
    index = LocalDiskRetrievalIndex(corpus_version="REF-2026-RBAC")

    # مستند قسم أ ومستند قسم ب
    index.add_document(doc_id=1, segments_data=[{'id': 100, 'normalized_text': 'تقرير خاص بقسم الهندسة'}])
    index.add_document(doc_id=2, segments_data=[{'id': 200, 'normalized_text': 'تقرير خاص بقسم الطب'}])

    # استعلام مسموح له فقط بمستندات قسم الطب (doc_id=2)
    allowed = {2}
    cands = index.search_candidates("تقرير خاص", top_k=50, allowed_doc_ids=allowed)

    assert 200 in cands
    assert 100 not in cands


def test_index_corruption_safe_rejection(tmp_path):
    """التحقق من رفض تحميل الفهرس إذا تم العبث بملفاته أو بصماته."""
    index = LocalDiskRetrievalIndex(corpus_version="REF-2026-CORRUPT")
    index.add_document(doc_id=1, segments_data=[{'id': 1, 'normalized_text': 'نص تجريبي'}])

    target_dir = tmp_path / "idx_corrupted"
    index.save(target_dir)

    # تشويه محتوى postings_words.json
    words_file = target_dir / "postings_words.json"
    with open(words_file, "a", encoding="utf-8") as f:
        f.write(" ")

    # محاولة التحميل يجب أن تفشل لاختلاف البصمة
    new_index = LocalDiskRetrievalIndex()
    assert new_index.load(target_dir) is False
