"""
Tests for Authoritative Mathematical Weighted Aggregation of Multi-Part Theses.
Guarantees that combined percentages equal sum(words) / sum(clean_words)
and strictly forbids misleading simple unweighted averages.
"""
import json
import pytest
from app import create_app
from app.models.schema import LegacyReport
from app.models.research_schema import Thesis, ThesisPart
from app.services.thesis_service import generate_combined_thesis_report
from app.repositories import report_repo
from app.repositories.base_repo import get_session as get_db_session


@pytest.fixture
def app_instance():
    app = create_app()
    app.config['TESTING'] = True
    return app


def test_authoritative_weighted_aggregation_math(app_instance):
    """
    Mathematical Proof Test:
    Part 1: 10,000 clean words, 500 problematic words (5.0% problematic)
    Part 2: 1,000 clean words, 800 problematic words (80.0% problematic)
    
    Total Analyzable Clean Words = 11,000
    Total Problematic Words = 1,300
    
    Authoritative Weighted Similarity = (1,300 / 11,000) * 100 = 11.8181...% -> 11.82%
    Flawed Unweighted Average = (5.0% + 80.0%) / 2 = 42.50%
    """
    # 1. Create Report 1 (10,000 words, 500 copied -> 5% problematic)
    rep1_data = {
        'id': 'rep_test_part1_10k',
        'title': 'الجزء الأول: 10000 كلمة',
        'author': 'باحث اختبار الرياضيات',
        'total_words': 10000,
        'clean_words_count': 10000,
        'copied_words': 500,
        'paraphrased_words': 0,
        'problematic_words': 500,
        'problematic_pct': 5.0,
        'overall_pct': 5.0,
        'copied_pct': 5.0,
        'paraphrase_pct': 0.0,
        'cited_pct': 0.0,
        'cited_words': 0
    }
    report_repo.save_report(
        report_id='rep_test_part1_10k',
        title='الجزء الأول: 10000 كلمة',
        overall_pct=5.0,
        copied_pct=5.0,
        para_pct=0.0,
        report_dict=rep1_data,
        status='مفحوص',
        author='باحث اختبار الرياضيات'
    )

    # 2. Create Report 2 (1,000 words, 800 copied -> 80% problematic)
    rep2_data = {
        'id': 'rep_test_part2_1k',
        'title': 'الجزء الثاني: 1000 كلمة',
        'author': 'باحث اختبار الرياضيات',
        'total_words': 1000,
        'clean_words_count': 1000,
        'copied_words': 800,
        'paraphrased_words': 0,
        'problematic_words': 800,
        'problematic_pct': 80.0,
        'overall_pct': 80.0,
        'copied_pct': 80.0,
        'paraphrase_pct': 0.0,
        'cited_pct': 0.0,
        'cited_words': 0
    }
    report_repo.save_report(
        report_id='rep_test_part2_1k',
        title='الجزء الثاني: 1000 كلمة',
        overall_pct=80.0,
        copied_pct=80.0,
        para_pct=0.0,
        report_dict=rep2_data,
        status='مفحوص',
        author='باحث اختبار الرياضيات'
    )

    with get_db_session() as session:
        # Create Thesis
        thesis = Thesis(
            reference_number='THS-2026-999001',
            title='دراسة تجريبية للأوزان النسبية للرسائل العلمية',
            author='باحث اختبار الرياضيات',
            degree_type='phd'
        )
        session.add(thesis)
        session.flush()

        # Attach as Thesis Parts
        part1 = ThesisPart(
            thesis_id=thesis.id,
            part_title='الفصل الأول الكبير',
            sort_order=1,
            original_filename='chap1.docx',
            stored_filename='chap1.docx',
            file_path='chap1.docx',
            file_hash='hash1',
            file_size_bytes=10000,
            report_id='rep_test_part1_10k',
            scan_status='completed'
        )
        part2 = ThesisPart(
            thesis_id=thesis.id,
            part_title='الفصل الثاني الصغير',
            sort_order=2,
            original_filename='chap2.docx',
            stored_filename='chap2.docx',
            file_path='chap2.docx',
            file_hash='hash2',
            file_size_bytes=1000,
            report_id='rep_test_part2_1k',
            scan_status='completed'
        )
        session.add_all([part1, part2])
        session.commit()
        thesis_id = thesis.id

    # Generate Combined Report
    success, comb, msg = generate_combined_thesis_report(thesis_id)
    assert success is True
    assert comb is not None

    # Assert totals
    assert comb.get('total_words') == 11000
    assert comb.get('problematic_words') == 1300
    assert len(comb.get('part_summaries', [])) == 2

    # Assert EXACT Weighted Percentage: 11.8%
    assert comb.get('problematic_pct') == 11.8
    assert comb.get('overall_pct') == 11.8

    # Strictly verify it is NOT the simple average (42.5%)
    assert comb.get('problematic_pct') != 42.5
    assert abs(comb.get('problematic_pct') - 11.8) < 0.1

    # Check parts breakdown totals
    summaries = comb.get('part_summaries', [])
    assert len(summaries) == 2
    assert summaries[0]['total_words'] == 10000
    assert summaries[1]['total_words'] == 1000
