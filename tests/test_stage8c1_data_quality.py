from plagiarism_detector.ai_detection.quality_audit import audit_records


def test_triage_finds_quality_and_group_risks():
    records = [
        {'sample_id': 'a', 'document_id': 'same', 'text': 'نص عربي قصير', 'split': 'train', 'topic_id': 'topic', 'generator_family': 'g'},
        {'sample_id': 'b', 'document_id': 'same', 'text': 'نص عربي قصير', 'split': 'test', 'topic_id': 'topic', 'generator_family': 'g'},
        {'sample_id': 'c', 'document_id': 'other', 'text': '�', 'split': 'other'},
    ]
    result = audit_records(records, min_words=4)
    assert set(result['issues']['short_text']) == {'a', 'b', 'c'}
    assert result['issues']['replacement_character'] == ['c']
    assert result['issues']['non_arabic_text'] == ['c']
    assert result['issues']['missing_or_invalid_split'] == ['c']
    assert result['group_leakage']['has_leakage']
    assert result['exact_duplicate_groups']
    assert result['topic_and_generator_overlap']['topic_id']
    assert result['topic_and_generator_overlap']['generator_family']
