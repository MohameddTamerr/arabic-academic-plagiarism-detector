# -*- coding: utf-8 -*-
"""
مجموعة اختبارات انحدار التقييم الأكاديمي الشامل (Detection Evaluation Regression Suite - Phase 18 Evidence Gate):
- تضمن استقرار دقة كشف النسخ الحرفي والمعدل والاستشهادات النصية المعتمدة عبر الزمن.
- تتحقق من أن محرك التقييم يستهلك الإعدادات الإنتاجية الفعلية (Runtime Production Settings) دون تضارب.
- تتحقق من الصرامة العلمية في تقرير النموذج الدلالي (UNAVAILABLE عند غياب ملفات النموذج محلياً).
- تتحقق من صحة تصنيف مصادر البيانات (Dataset Origin Segregation) والتحقق من عدم وجود ادعاء مضلل لمراجعة الخبراء.
- تفصل مقاييس كشف الاستشهاد (Citation Detection) عن مقاييس تصنيف التطابق النصي (Overlap Classification).
- تتحقق من حتمية تجربة أوراكل المطابقة (Matcher-Oracle Experiment) لعزل إخفاق الاسترجاع عن إخفاق الخوارزمية.
- تضمن عدم حدوث أي تغيير في الإعدادات الإنتاجية الثابتة للمنظومة.
"""

import sys
import json
import pytest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.citations.citation_detector import detect_citation
from evaluation.evaluator import (
    evaluate_sample_components, run_full_benchmark,
    check_semantic_model_provenance, RUNTIME_PRODUCTION_CONFIG
)


def test_evaluator_consumes_runtime_production_configuration():
    """1. التحقق من أن محرك التقييم يستهلك الإعدادات الإنتاجية الفعلية لـ report_builder."""
    assert RUNTIME_PRODUCTION_CONFIG['shingle_size'] == config.DEFAULT_SETTINGS['shingle_size']
    assert RUNTIME_PRODUCTION_CONFIG['jaccard_threshold'] == config.DEFAULT_SETTINGS['jaccard_threshold']
    assert RUNTIME_PRODUCTION_CONFIG['tfidf_threshold'] == config.DEFAULT_SETTINGS['tfidf_threshold']
    assert RUNTIME_PRODUCTION_CONFIG['shingle_size'] == 5
    assert RUNTIME_PRODUCTION_CONFIG['jaccard_threshold'] == 0.40
    assert RUNTIME_PRODUCTION_CONFIG['tfidf_threshold'] == 0.40


def test_semantic_model_absence_reported_as_unavailable():
    """2. التحقق من أن غياب ملفات النموذج الدلالي محلياً يُسفر حتماً عن حالة UNAVAILABLE دون تزييف أو محاكاة."""
    prov = check_semantic_model_provenance()
    model_dir = Path(prov['local_model_path'])
    if not model_dir.exists() or not any(model_dir.iterdir()):
        assert prov['status'] == 'UNAVAILABLE'
        assert prov['samples_inferred'] == 0
        assert prov['is_simulated_or_hardcoded'] is False


def test_dataset_origin_audit_and_proportions():
    """3. التحقق من تدقيق مصادر البيانات وأن 100% من العينات موسومة بـ DEVELOPER_SYNTHETIC لغياب الاعتماد الخارجي."""
    dataset_file = _HERE / 'evaluation' / 'dataset.json'
    assert dataset_file.exists()

    with open(dataset_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)

    assert len(samples) == 323
    for s in samples:
        assert s['generation_origin'] == 'DEVELOPER_SYNTHETIC'
        assert s['review_status'] == 'unreviewed'


def test_citation_metrics_separated_from_overlap():
    """4. التحقق من فصل مقاييس كشف الاستشهاد عن مقاييس تصنيف التطابق النصي في التقييم."""
    res = run_full_benchmark()
    assert 'citation_metrics' in res
    assert 'overlap_classification_metrics' in res
    assert 'common_text_suppression_metrics' in res

    cite = res['citation_metrics']
    assert cite['precision'] >= 0.80
    assert cite['recall'] == 1.00
    assert cite['false_citation_rate'] <= 0.05


def test_matcher_oracle_experiment_determinism():
    """5. التحقق الحتمي من نتائج تجربة Matcher-Oracle وفصل إخفاق الاسترجاع عن إخفاق المطابقة."""
    res = run_full_benchmark()
    oracle = res['matcher_oracle_experiment']

    assert oracle['exact_copy_oracle_recall'] >= 0.95
    assert oracle['modified_copy_oracle_recall'] >= 0.65
    assert oracle['paraphrase_oracle_recall'] == 0.00
    assert 'lexical feature mismatch' in oracle['oracle_insight']


def test_paraphrase_distribution_measurements():
    """6. التحقق من احتواء تقرير التقييم على التوزيعات الإحصائية الحقيقية المقاسة لعينات إعادة الصياغة."""
    res = run_full_benchmark()
    dist = res['paraphrase_score_distributions']

    assert 'word_tfidf' in dist
    assert 'char_tfidf' in dist
    assert 'jaccard' in dist
    assert dist['semantic_score'] == 'UNAVAILABLE'

    # التحقق من أن القيم مقاسة إحصائياً وليست عشوائية
    assert dist['char_tfidf']['min'] > 0.15
    assert dist['char_tfidf']['median'] > 0.30
    assert dist['word_tfidf']['median'] == 0.0


def test_exact_copy_normalization_invariance():
    """7. التحقق من أن النسخ الحرفي يحقق تطابقاً تاماً عبر فروق التشكيل وعلامات الترقيم وتوحيد الألف."""
    ref = "يُعَدُّ الأَمْنُ السِّيبِرَانِيُّ دِرْعاً أَسَاسِيّاً لِحِمَايَةِ البِنْيَةِ التَّحْتِيَّةِ الحَرِجَةِ."
    query = "يعد الامن السيبراني درعا اساسيا لحماية البنية التحتية الحرجة"

    comp = evaluate_sample_components(query, ref)
    assert comp['is_identical_normalized'] is True
    assert comp['overlap_class'] == 'EXACT_COPY'
    assert comp['jaccard_score'] >= 0.90


def test_modified_copy_detection_boundary():
    """8. التحقق من كشف النسخ المعدل بالمرادفات الطفيفة ضمن حدود العتبة المعتمدة."""
    ref = "يتطلب التحقيق الجنائي الرقمي اتباع منهجية علمية صارمة لجمع الأدلة وتوثيقها وتحليلها لتقديمها إلى المحكمة."
    query = "يتطلب التحقيق الرقمي الجنائي تطبيق منهجية عملية صارمة لاستخراج الأدلة وحفظها وتحليلها لرفعها إلى المحكمة."

    comp = evaluate_sample_components(query, ref)
    assert comp['overlap_class'] in ('EXACT_COPY', 'MODIFIED_COPY')
    assert comp['shingle_score'] >= 0.40 or comp['jaccard_score'] >= 0.35


def test_properly_cited_quote_recognition():
    """9. التحقق من التعرف الحتمي على الاقتباسات الموثقة وتصنيفها كـ CITED_SEGMENT في مسار الإنتاج."""
    query = "\"إن الأمن الوطني لم يعد مقتصراً على البعد العسكري فحسب بل امتد ليشمل الأبعاد الاقتصادية\" (العمري، 2021، ص. 45)."
    ref = "إن الأمن الوطني لم يعد مقتصراً على البعد العسكري فحسب بل امتد ليشمل الأبعاد الاقتصادية والبيئية."

    comp = evaluate_sample_components(query, ref)
    assert comp['citation_detected'] is True
    assert comp['production_pipeline_action'] == 'CITED_SEGMENT'


def test_false_citation_resilience():
    """10. التحقق من أن التواريخ والنسب المئوية وأرقام المواد القانونية لا تُعامل خطأً كاستشهادات مرجعية."""
    non_citation_texts = [
        "صدر المرسوم الملكي بتاريخ 1445/05/12هـ الموافق 2023/11/26م لتنظيم الهيئة.",
        "بلغت نسبة إنجاز المشروع 85% مقارنة بالعام الماضي.",
        "تنص المادة رقم 25 من اللائحة التنفيذية على شروط الترقية.",
        "في الصفحة رقم 120 تم استعراض ملخص الجداول الإحصائية."
    ]

    for text in non_citation_texts:
        cite = detect_citation(text)
        assert cite.is_cited is False, f"خطأ: تم اعتبار النص التالي استشهاداً مرجعياً بطريق الخطأ: {text}"


def test_unrelated_texts_zero_similarity():
    """11. التحقق من أن النصوص المنفصلة من مجالات متباعدة تسجل درجة تشابه منخفضة وتصنف كـ ORIGINAL_UNRELATED."""
    ref = "تعتمد الزراعة المائية الحديثة على تدوير المحاليل الغذائية لتغذية النباتات في بيئات محمية دون الحاجة إلى التربة."
    query = "يُعتبر عقد المقاولة من عقود المعاوضة الملزمة للجانبين والتي يرتب عليها القانون التزامات متقابلة بين المقاول والمالك."

    comp = evaluate_sample_components(query, ref)
    assert comp['overlap_class'] == 'ORIGINAL_UNRELATED'
    assert comp['jaccard_score'] == 0.0
    assert comp['shingle_score'] == 0.0
    assert comp['tfidf_score'] < 0.15


def test_evaluation_reproducibility():
    """12. التحقق الحتمي من استنساخ نتائج التقييم (Evaluation Reproducibility) وتطابق النتائج عبر جولتين متتاليتين."""
    res1 = run_full_benchmark()
    res2 = run_full_benchmark()

    assert res1['overall_metrics']['total_samples'] == res2['overall_metrics']['total_samples']
    assert res1['overall_metrics']['total_correct'] == res2['overall_metrics']['total_correct']
    assert res1['overall_metrics']['overall_accuracy'] == res2['overall_metrics']['overall_accuracy']
    assert res1['overall_metrics']['macro_f1'] == res2['overall_metrics']['macro_f1']
    assert res1['overlap_confusion_matrix'] == res2['overlap_confusion_matrix']


def test_production_thresholds_unmutated():
    """13. التحقق الصارم من عدم تعديل أي عتبة إنتاجية أو تغيير في إعدادات المنظومة الافتراضية."""
    assert config.DEFAULT_SETTINGS['jaccard_threshold'] == 0.40
    assert config.DEFAULT_SETTINGS['tfidf_threshold'] == 0.40
    assert config.DEFAULT_SETTINGS['shingle_size'] == 5
    assert config.DEFAULT_SETTINGS['enable_semantic_model'] is False
