from pathlib import Path

from app import versioning
from plagiarism_detector.detection.persistent_retrieval import (
    load_or_reconcile_index,
    map_persistent_candidates,
)


def _segments() -> list[dict]:
    return [
        {
            'seg_id': 101, 'doc_id': 1, 'page_number': 1, 'segment_number': 1,
            'raw_text': 'الذكاء الاصطناعي يدعم البحث العلمي في الجامعات العربية',
            'normalized_text': 'الذكاء الاصطناعي يدعم البحث العلمي في الجامعات العربية',
        },
        {
            'seg_id': 202, 'doc_id': 2, 'page_number': 2, 'segment_number': 1,
            'raw_text': 'تتناول الدراسة الطاقة المتجددة وسياسات الاستدامة البيئية',
            'normalized_text': 'تتناول الدراسة الطاقة المتجددة وسياسات الاستدامة البيئية',
        },
    ]


def test_disk_index_loads_across_restart_and_maps_stable_segment_ids(tmp_path):
    segments = _segments()
    index_dir = tmp_path / 'retrieval-index'
    built, first = load_or_reconcile_index(segments, 'REF-A', 'corpus-a', index_dir)
    assert first['rebuilt'] is True
    assert built.normalization_version == versioning.NORMALIZATION_VERSION

    loaded, second = load_or_reconcile_index(segments, 'REF-A', 'corpus-a', index_dir)
    assert second['loaded_from_disk'] is True
    positions = {101: 0, 202: 1}
    assert map_persistent_candidates(loaded, 'البحث العلمي والذكاء الاصطناعي', positions, 10)[0] == 0


def test_incremental_update_and_delete_reconcile_without_duplicate_indexing(tmp_path):
    index_dir = tmp_path / 'retrieval-index'
    segments = _segments()
    first, _ = load_or_reconcile_index(segments, 'REF-A', 'corpus-a', index_dir)
    assert first.total_documents == 2

    changed = [segments[0], {
        'seg_id': 303, 'doc_id': 3, 'page_number': 1, 'segment_number': 1,
        'raw_text': 'المكتبات الرقمية تحفظ الرسائل الجامعية العربية',
        'normalized_text': 'المكتبات الرقمية تحفظ الرسائل الجامعية العربية',
    }]
    reconciled, info = load_or_reconcile_index(changed, 'REF-B', 'corpus-b', index_dir)
    assert info['changed_documents'] == 2  # retired doc 2 and new doc 3
    assert reconciled.total_documents == 2
    assert 202 not in reconciled.search_candidates('الطاقة المتجددة')
    assert 303 in reconciled.search_candidates('المكتبات الرقمية العربية')

    again, _ = load_or_reconcile_index(changed, 'REF-B', 'corpus-b', index_dir)
    assert again.total_documents == 2
    assert again.total_segments == 2


def test_changed_segments_trigger_stale_reconciliation_and_corrupt_index_rebuild(tmp_path):
    index_dir = tmp_path / 'retrieval-index'
    segments = _segments()
    load_or_reconcile_index(segments, 'REF-A', 'corpus-a', index_dir)
    changed = [dict(item) for item in segments]
    changed[0]['normalized_text'] = 'الذكاء الاصطناعي وتحليل البيانات في الجامعات العربية'
    updated, info = load_or_reconcile_index(changed, 'REF-A', 'corpus-a', index_dir)
    assert info['changed_documents'] == 1
    assert 101 in updated.search_candidates('تحليل البيانات')

    # Checksum rejection must rebuild from current supplied rows, never trust
    # the corrupt payload.
    (index_dir / 'postings_words.json').write_text('{broken', encoding='utf-8')
    recovered, status = load_or_reconcile_index(changed, 'REF-A', 'corpus-a', index_dir)
    assert status['rebuilt'] is True
    assert recovered.search_candidates('تحليل البيانات')[0] == 101


def test_empty_corpus_is_persisted_and_searchable_as_empty(tmp_path):
    index, status = load_or_reconcile_index([], 'REF-EMPTY', 'empty', tmp_path / 'empty-index')
    assert status['rebuilt'] is True
    assert index.total_segments == 0
    assert index.search_candidates('استعلام عربي') == []


def test_duplicate_document_reconciliation_is_idempotent_and_source_files_are_not_read(tmp_path):
    # The index is built exclusively from DB-extracted segment rows; an absent
    # original upload must not be opened by retrieval.
    segments = _segments()
    segments[0]['file_path'] = str(tmp_path / 'missing-source.pdf')
    index_dir = tmp_path / 'index'
    first, _ = load_or_reconcile_index(segments, 'REF-A', 'corpus-a', index_dir)
    second, status = load_or_reconcile_index(segments, 'REF-A', 'corpus-a', index_dir)
    assert first.total_documents == second.total_documents == 2
    assert second.total_segments == 2
    assert status['changed_documents'] == 0
    first_rank = second.search_candidates('البحث العلمي والذكاء الاصطناعي')
    assert first_rank == second.search_candidates('البحث العلمي والذكاء الاصطناعي')
