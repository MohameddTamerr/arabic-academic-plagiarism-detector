from plagiarism_detector.citations.citation_intelligence import extract_citations, link_citations, parse_bibliography_segments


def _entries():
    return parse_bibliography_segments([
        {'text': 'قائمة المراجع', 'is_bibliography': True},
        {'text': '1. درويش، 2023. الأمن الإنساني. دار المعرفة.', 'is_bibliography': True},
        {'text': '2. العلي، 2020. الإدارة العامة. ناشر.', 'is_bibliography': True},
        {'text': '3. العلي، 2020. إدارة المؤسسات. ناشر.', 'is_bibliography': True},
    ])


def test_author_year_offsets_and_linking_preserve_original_text():
    text = 'تؤكد النتائج (درويش، 2023، ص. ٤٥) أهمية المراجعة.'
    citation = extract_citations(text)[0]
    assert text[citation['start']:citation['end']] == citation['text']
    assert citation['year'] == '2023'
    assert citation['pages'] == '45'
    assert link_citations([citation], _entries())[0]['status'] == 'LINKED'


def test_multiple_and_numeric_citations_are_explicit_not_silently_merged():
    text = 'تتفق الدراسات (درويش، 2023؛ العلي، 2020) [1، 2، ص. 5].'
    citations = extract_citations(text)
    assert len(citations) == 3
    assert any(item['citation_type'] == 'numeric' for item in citations)
    links = link_citations(citations, _entries())
    assert any(item['status'] == 'AMBIGUOUS' for item in links)


def test_missing_and_ambiguous_references_remain_uncertain():
    entries = _entries()
    missing = extract_citations('وفقاً لـ(الشمري، 2019) تتطور السياسات.')
    assert link_citations(missing, entries)[0]['status'] == 'UNRESOLVED'
    ambiguous = extract_citations('تتباين الآراء (العلي، 2020).')
    assert link_citations(ambiguous, entries)[0]['status'] == 'AMBIGUOUS'
    assert link_citations(missing, [])[0]['status'] == 'NO_REFERENCE_FOUND'


def test_bibliography_parser_keeps_unknown_metadata_empty_and_mixed_doi():
    entries = parse_bibliography_segments([
        {'text': 'Smith & Jones, 2020. Mixed Methods. Academic Press. doi:10.1000/test', 'is_bibliography': True}
    ])
    assert entries[0]['doi'] == '10.1000/test'
    assert entries[0]['journal'] is None
    assert entries[0]['original_text'].startswith('Smith')
