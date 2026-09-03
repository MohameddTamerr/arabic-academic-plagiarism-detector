# -*- coding: utf-8 -*-
"""
محرك بناء التقرير الأكاديمي الشامل (Academic Report Builder & Detection Pipeline):
- يربط كافة مراحل الفحص: كشف التحايل، استخراج الاقتباسات، استبعاد المراجع، والمطابقة متعددة المراحل.
- يحفظ أرقام الصفحات المصدرية الحقيقية (Page Attribution) لكل جملة متطابقة.
- يقدم نسبة الاستلال الإجمالية (Total Similarity) ونسبة الاستلال المسببة للقلق (Problematic Similarity).
- يحسب الصفحات التقديرية (Estimated Pages) وتنبيه تجاوز الحد الأقصى للمصدر الواحد.
"""

import logging
from collections import defaultdict
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer

import config
from app.repositories import document_repo
from plagiarism_detector.preprocessing.normalizer import (
    normalize_light, normalize_aggressive, split_sentences, get_shingles
)
from plagiarism_detector.preprocessing.cheating_detector import (
    detect_cheating_manipulation, clean_cheating_text
)
from plagiarism_detector.preprocessing.segmenter import segment_pages, DocumentSegment
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.citations.bibliography_detector import filter_bibliography_sections
from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.detection.semantic_matcher import match_semantic_similarity
from plagiarism_detector.ai_analysis.stylistic_indicators import analyze_stylistic_ai_indicators
from plagiarism_detector.reporting.page_allowance import compute_source_allowance

logger = logging.getLogger(__name__)

# كاش الفهرس في الذاكرة لتسريع الفحوصات المتتالية
_CACHED_INDEX = None


def build_pipeline_index() -> dict:
    """
    بناء فهرس الاسترجاع السريع للمقاطع المرجعية من قاعدة البيانات.
    يتم بناؤه مرة واحدة وتحديثه عند إضافة أو حذف أبحاث.
    """
    global _CACHED_INDEX
    logger.info("جاري استخراج المقاطع وبناء فهرس الفحص الأكاديمي...")

    raw_segments = document_repo.get_all_segments_for_index()

    retriever = CandidateRetriever()
    corpus_shingles = []
    corpus_light_texts = []
    corpus_aggr_texts = []
    corpus_metadata = []

    shingle_size = config.DEFAULT_SETTINGS['shingle_size']

    for idx, seg in enumerate(raw_segments):
        raw_text = seg['raw_text']
        n_light = seg.get('normalized_text') or normalize_light(raw_text)
        n_aggr = normalize_aggressive(raw_text)

        words_light = n_light.split()
        shingles = get_shingles(n_aggr, size=shingle_size)

        retriever.add_segment(idx, words_light, shingles)

        corpus_shingles.append(shingles)
        corpus_light_texts.append(n_light)
        corpus_aggr_texts.append(n_aggr)
        corpus_metadata.append({
            'doc_id': seg['doc_id'],
            'title': seg['title'],
            'author': seg.get('author', ''),
            'page_number': seg.get('page_number'),  # رقم الصفحة المصدرية الحقيقي
            'raw_text': raw_text
        })

    # بناء مصفوفة TF-IDF مسبقة للمقاطع إن وجدت نصوص
    vectorizer = None
    tfidf_matrix = None
    if corpus_light_texts:
        try:
            vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
            tfidf_matrix = vectorizer.fit_transform(corpus_light_texts)
        except Exception as e:
            logger.debug(f"تخطي بناء مصفوفة TF-IDF الشاملة: {e}")

    index_data = {
        'retriever': retriever,
        'corpus_shingles': corpus_shingles,
        'corpus_light_texts': corpus_light_texts,
        'corpus_aggr_texts': corpus_aggr_texts,
        'corpus_metadata': corpus_metadata,
        'vectorizer': vectorizer,
        'tfidf_matrix': tfidf_matrix,
        'total_segments': len(raw_segments)
    }

    _CACHED_INDEX = index_data
    logger.info(f"تم بناء الفهرس بنجاح: {len(raw_segments)} مقطع مرجعي.")
    return index_data


def get_pipeline_index() -> dict:
    """استرجاع الفهرس المخزن في الذاكرة أو إعادة بنائه إن لم يكن جاهزاً."""
    global _CACHED_INDEX
    if _CACHED_INDEX is None:
        _CACHED_INDEX = build_pipeline_index()
    return _CACHED_INDEX


def invalidate_pipeline_index():
    """إلغاء الفهرس المؤقت لإعادة بنائه عند تغيير الأبحاث."""
    global _CACHED_INDEX
    _CACHED_INDEX = None


def analyze_academic_document(
    raw_text: str,
    pages_data: Optional[list[dict]] = None,
    settings_override: Optional[dict] = None
) -> dict:
    """
    إجراء الفحص الأكاديمي الشامل للنص أو الصفحات المستخرجة.
    """
    settings = dict(config.DEFAULT_SETTINGS)
    if settings_override:
        settings.update(settings_override)

    # 1. كشف التلاعب وتنقية النص
    cheating_res = detect_cheating_manipulation(raw_text)
    cleaned_text = clean_cheating_text(raw_text)

    # 2. مؤشرات أسلوب الذكاء الاصطناعي الاستئناسية
    ai_indicators = analyze_stylistic_ai_indicators(cleaned_text)

    # 3. تقطيع النص لفقرات مع الحفاظ على الصفحات
    if pages_data:
        segments_list = segment_pages(pages_data, min_words=settings['min_sentence_words'])
    else:
        # إذا ورد نص خالص بدون صفحات
        sents = split_sentences(cleaned_text, min_words=settings['min_sentence_words'])
        segments_list = [
            DocumentSegment(
                segment_number=i + 1,
                page_number=None,
                raw_text=s,
                normalized_light=normalize_light(s),
                normalized_aggressive=normalize_aggressive(s),
                word_count=len(s.split())
            )
            for i, s in enumerate(sents)
        ]

    index_data = get_pipeline_index()
    retriever: CandidateRetriever = index_data['retriever']
    corpus_shingles = index_data['corpus_shingles']
    corpus_light_texts = index_data['corpus_light_texts']
    corpus_aggr_texts = index_data['corpus_aggr_texts']
    corpus_metadata = index_data['corpus_metadata']
    vectorizer = index_data['vectorizer']
    tfidf_matrix = index_data['tfidf_matrix']

    total_words = 0
    copied_words = 0
    para_words = 0
    cited_words = 0
    problematic_words = 0

    # تتبع الكلمات والصفحات لكل مصدر
    words_by_source: dict[int, int] = defaultdict(int)
    pages_by_source: dict[int, set[Optional[int]]] = defaultdict(set)
    source_info: dict[int, dict] = {}

    processed_segments = []

    for seg in segments_list:
        w_count = seg.word_count
        total_words += w_count

        seg_dict = {
            'text': seg.raw_text,
            'page_number': seg.page_number,
            'status': 'original',
            'match_type': 'ORIGINAL',
            'score': 0,
            'pct': 0,
            'source_id': None,
            'source_title': '',
            'source_author': '',
            'source_page': None,
            'source_page_display': 'غير متاح',
            'matched_text': '',
            'is_cited': False,
            'citation_detail': ''
        }

        # فحص وجود استشهاد أو علامات تنصيص
        citation_check = detect_citation(seg.raw_text)
        if citation_check.is_cited:
            seg_dict['is_cited'] = True
            seg_dict['citation_detail'] = citation_check.citation_detail

        if not index_data['corpus_metadata']:
            processed_segments.append(seg_dict)
            continue

        # ── المرحلة A: كشف النسخ الحرفي عبر Shingles + Jaccard ───
        q_shingles = get_shingles(seg.normalized_aggressive, size=settings['shingle_size'])
        shingle_candidates = retriever.retrieve_candidates_for_shingles(q_shingles)

        match_found = False

        if shingle_candidates:
            res_a = match_exact_or_near_copy(
                query_shingles=q_shingles,
                query_norm_text=seg.normalized_aggressive,
                candidate_indices=shingle_candidates,
                corpus_shingles=corpus_shingles,
                corpus_norm_texts=corpus_aggr_texts,
                threshold=settings['jaccard_threshold']
            )
            if res_a:
                cand_idx, score, m_type = res_a
                meta = corpus_metadata[cand_idx]
                doc_id = meta['doc_id']
                p_score = min(round(score * 100), 100)

                seg_dict['source_id'] = doc_id
                seg_dict['source_title'] = meta['title']
                seg_dict['source_author'] = meta['author']
                seg_dict['source_page'] = meta['page_number']
                seg_dict['source_page_display'] = f"ص. {meta['page_number']}" if meta['page_number'] else "غير متاح"
                seg_dict['matched_text'] = meta['raw_text']
                seg_dict['score'] = score
                seg_dict['pct'] = p_score

                if seg_dict['is_cited']:
                    seg_dict['status'] = 'cited'
                    seg_dict['match_type'] = 'CITED MATCH'
                    cited_words += w_count
                else:
                    seg_dict['status'] = 'copied'
                    seg_dict['match_type'] = 'DIRECT COPY'
                    copied_words += w_count
                    problematic_words += w_count

                words_by_source[doc_id] += w_count
                pages_by_source[doc_id].add(meta['page_number'])
                source_info[doc_id] = {'title': meta['title'], 'author': meta['author']}
                match_found = True

        # ── المرحلة B: كشف إعادة الصياغة عبر TF-IDF ───────────────
        if not match_found:
            token_candidates = retriever.retrieve_candidates_by_tokens(
                seg.normalized_light.split(),
                top_k=settings['max_candidate_retrieval']
            )
            if token_candidates:
                res_b = match_lexical_paraphrase(
                    query_norm_text=seg.normalized_light,
                    candidate_indices=token_candidates,
                    corpus_norm_texts=corpus_light_texts,
                    threshold=settings['tfidf_threshold'],
                    vectorizer=vectorizer,
                    corpus_tfidf_matrix=tfidf_matrix
                )
                if res_b:
                    cand_idx, score, m_type = res_b
                    meta = corpus_metadata[cand_idx]
                    doc_id = meta['doc_id']
                    p_score = min(round(score * 100), 100)

                    seg_dict['source_id'] = doc_id
                    seg_dict['source_title'] = meta['title']
                    seg_dict['source_author'] = meta['author']
                    seg_dict['source_page'] = meta['page_number']
                    seg_dict['source_page_display'] = f"ص. {meta['page_number']}" if meta['page_number'] else "غير متاح"
                    seg_dict['matched_text'] = meta['raw_text']
                    seg_dict['score'] = score
                    seg_dict['pct'] = p_score

                    if seg_dict['is_cited']:
                        seg_dict['status'] = 'cited'
                        seg_dict['match_type'] = 'CITED PARAPHRASE'
                        cited_words += w_count
                    else:
                        seg_dict['status'] = 'paraphrased'
                        seg_dict['match_type'] = 'POSSIBLE PARAPHRASE'
                        para_words += w_count
                        problematic_words += w_count

                    words_by_source[doc_id] += w_count
                    pages_by_source[doc_id].add(meta['page_number'])
                    source_info[doc_id] = {'title': meta['title'], 'author': meta['author']}
                    match_found = True

        # ── المرحلة C: التشابه الدلالي (اختياري) ───────────────────
        if not match_found and settings.get('enable_semantic_model', False):
            # تُجرى فقط على المرشحين
            pass

        processed_segments.append(seg_dict)

    # 4. فحص واستبعاد أقسام المراجع الببليوغرافية
    processed_segments, bib_count = filter_bibliography_sections(processed_segments)

    # 5. حساب الإجماليات بدقة رياضية بعد استبعاد المراجع الببليوغرافية
    copied_words = 0
    para_words = 0
    cited_words = 0
    problematic_words = 0
    clean_total_words = 0

    for seg in processed_segments:
        w_cnt = len(seg['text'].split())
        clean_total_words += w_cnt

        if seg.get('is_bibliography'):
            # استبعاد فقرات المراجع من الاستلال الإشكالي والنسخ
            continue

        if seg['status'] == 'copied':
            copied_words += w_cnt
            problematic_words += w_cnt
        elif seg['status'] == 'paraphrased':
            para_words += w_cnt
            problematic_words += w_cnt
        elif seg['status'] == 'cited':
            cited_words += w_cnt

    total_safe_words = max(clean_total_words, 1)
    matched_total_words = copied_words + para_words + cited_words

    # ضمان النسب الرياضية الدقيقة: 0 <= % <= 100 و problematic <= overall
    overall_pct = min(round((matched_total_words / total_safe_words) * 100, 1), 100.0)
    problematic_pct = min(round((problematic_words / total_safe_words) * 100, 1), overall_pct)
    copied_pct = min(round((copied_words / total_safe_words) * 100, 1), 100.0)
    paraphrase_pct = min(round((para_words / total_safe_words) * 100, 1), 100.0)
    cited_pct = min(round((cited_words / total_safe_words) * 100, 1), 100.0)

    # 6. تفاصيل المصادر ومنطق الصفحات المسموحة (Phase 8)
    sources_list = []
    exceeded_sources = []
    for s_id, s_words in words_by_source.items():
        s_title = source_info[s_id]['title']
        s_author = source_info[s_id]['author']
        s_pages_set = pages_by_source[s_id]

        allowance = compute_source_allowance(
            source_id=s_id,
            source_title=s_title,
            source_author=s_author,
            matched_words=s_words,
            matched_pages_set=s_pages_set,
            words_per_page=settings['words_per_page'],
            max_allowed_pages=settings['max_allowed_pages_per_source']
        )
        allowance['pct'] = round((s_words / total_safe_words) * 100, 1)
        sources_list.append(allowance)

        if allowance['is_limit_exceeded']:
            exceeded_sources.append(allowance)

    sources_list.sort(key=lambda x: x['matched_words'], reverse=True)

    page_limit_alert = {
        'has_limit_exceeded': len(exceeded_sources) > 0,
        'max_allowed_pages': settings['max_allowed_pages_per_source'],
        'exceeded_sources': exceeded_sources,
        'details': [s['alert_message'] for s in exceeded_sources]
    }

    return {
        'overall_pct': overall_pct,               # النسبة الكلية للاستلال
        'problematic_pct': problematic_pct,       # نسبة الاستلال المشبوهة (غير الموثقة)
        'copied_pct': copied_pct,                 # نسبة النسخ الحرفي
        'paraphrase_pct': paraphrase_pct,         # نسبة إعادة الصياغة
        'cited_pct': cited_pct,                   # نسبة الاقتباس الموثق السليم
        'total_words': total_words,
        'copied_words': copied_words,
        'paraphrased_words': para_words,
        'cited_words': cited_words,
        'problematic_words': problematic_words,
        'segments': processed_segments,
        'sources': sources_list,
        'cheating': cheating_res,
        'ai_analysis': ai_indicators,
        'page_limit_alert': page_limit_alert,
        'bibliography_segments_count': bib_count
    }
