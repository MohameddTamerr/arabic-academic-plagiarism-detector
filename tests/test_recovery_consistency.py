"""Recovery invariants using isolated data and safe scanner doubles."""
import subprocess
from types import SimpleNamespace
import pytest

from app.services import upload_validation_service as validation
from app.errors.exceptions import ValidationError
from plagiarism_detector.reporting import report_builder as builder
from plagiarism_detector.preprocessing.normalizer import get_shingles


@pytest.mark.parametrize('k', [4, 5])
def test_scan_reference_and_query_use_same_k(k, monkeypatch):
    text = 'هذا البحث يناقش حماية المعلومات في المؤسسات الأكاديمية الحديثة'
    index = builder.build_pipeline_index()
    retriever = builder.CandidateRetriever()
    retriever.add_segment(0, text.split(), get_shingles(text, size=4), norm_light=text)
    index = dict(index, corpus_light_texts=[text], corpus_aggr_texts=[text],
                 retriever=retriever,
                 corpus_shingles=[get_shingles(text, size=4)],
                 corpus_metadata=[{'doc_id': 987654, 'title': 'Reference', 'author': '', 'raw_text': text,
                                   'page_number': 3}], vectorizer=None, tfidf_matrix=None)
    monkeypatch.setattr(builder, '_CACHED_INDEX', index)
    effective = builder.get_pipeline_index(shingle_size=k)
    assert effective['shingle_size'] == k
    assert effective['corpus_shingles'][0] == get_shingles(text, size=k)
    assert all(len(s) == k for s in effective['corpus_shingles'][0])
    calls = []
    query_sizes = []
    original_shingles = builder.get_shingles
    def observed_shingles(value, size):
        query_sizes.append(size)
        return original_shingles(value, size=size)
    monkeypatch.setattr(builder, 'get_shingles', observed_shingles)
    original = builder.get_pipeline_index
    def observed(*args, **kwargs):
        calls.append(kwargs['shingle_size'])
        return original(*args, **kwargs)
    monkeypatch.setattr(builder, 'get_pipeline_index', observed)
    builder.analyze_academic_document(text, settings_override={'shingle_size': k})
    assert calls == [k]
    assert query_sizes and set(query_sizes) == {k}
    assert index['shingle_size'] == 4


def test_permission_helpers_preserve_sysadmin_aliases():
    from app.security.permissions import has_permission, get_user_permissions, Permission
    for role in ['system_admin','SYSADMIN','admin']:
        assert has_permission(role, Permission.REVIEW_FINAL)
        assert Permission.USERS_MANAGE in get_user_permissions({'role':role})
    assert not has_permission('employee', Permission.REVIEW_FINAL)


@pytest.mark.parametrize('response', ['clean', 'threat', 'unavailable', 'timeout', 'exception', 'unknown', 'error'])
def test_antivirus_failure_never_promotes(tmp_path, monkeypatch, response):
    monkeypatch.setattr(validation.storage_service, 'get_staging_upload_dir', lambda: tmp_path)
    monkeypatch.setattr(validation, '_find_antivirus_engine', lambda: None if response == 'unavailable' else 'clamscan')
    def scan(*args, **kwargs):
        if response == 'timeout':
            raise subprocess.TimeoutExpired('clamscan', 60)
        if response == 'exception':
            raise OSError('safe mocked scanner error')
        code = {'clean': 0, 'threat': 1, 'unknown': 0, 'error': 2}[response]
        return SimpleNamespace(returncode=code, stdout=(str(args[0][-1]) + ': OK').encode() if response == 'clean' else b'unknown', stderr=b'')
    monkeypatch.setattr(validation.subprocess, 'run', scan)
    if response == 'clean':
        result = validation.validate_and_stage_upload(b'Safe academic test content', 'safe.txt')
        assert result['antivirus_status'] == 'SCAN_CLEAN'
        validation.cleanup_staging_file(result['staging_path'])
    else:
        with pytest.raises(ValidationError):
            validation.validate_and_stage_upload(b'Safe academic test content', 'safe.txt')
    assert list(tmp_path.iterdir()) == []
