# -*- coding: utf-8 -*-
"""
محرك بناء التقرير الأكاديمي الشامل (Academic Report Builder & Detection Pipeline):
- يربط كافة مراحل الفحص: كشف التحايل، استخراج الاقتباسات، استبعاد المراجع، والمطابقة متعددة المراحل.
- يحفظ أرقام الصفحات المصدرية الحقيقية (Page Attribution) لكل جملة متطابقة.
- يقدم نسبة الاستلال الإجمالية (Total Similarity) ونسبة الاستلال المسببة للقلق (Problematic Similarity).
- يحسب الصفحات التقديرية (Estimated Pages) وتنبيه تجاوز الحد الأقصى للمصدر الواحد.
"""

import logging
import hashlib
import os
from collections import defaultdict
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer

import config
from app.repositories import document_repo, report_repo
from plagiarism_detector.preprocessing.normalizer import (
    normalize_light, normalize_aggressive, split_sentences, get_shingles
)
from plagiarism_detector.preprocessing.cheating_detector import (
    detect_cheating_manipulation, clean_cheating_text
)
from plagiarism_detector.preprocessing.segmenter import segment_pages, DocumentSegment
from plagiarism_detector.citations.citation_detector import detect_citation
from plagiarism_detector.citations.bibliography_detector import filter_bibliography_sections
from plagiarism_detector.filters.common_phrases import filter_common_spans
from plagiarism_detector.detection.candidate_retriever import CandidateRetriever
from plagiarism_detector.detection.shingle_matcher import match_exact_or_near_copy
from plagiarism_detector.detection.tfidf_matcher import match_lexical_paraphrase
from plagiarism_detector.detection.evidence_gate import (
    accept_lexical_paraphrase,
    accept_semantic_paraphrase,
)
from plagiarism_detector.detection.review_history_matcher import (
    build_review_history_index,
    match_review_history_segment,
)
from plagiarism_detector.detection.semantic_matcher import (
    check_semantic_model_availability,
    compute_embeddings,
    match_semantic_similarity,
)
from plagiarism_detector.ai_analysis.stylistic_indicators import analyze_stylistic_ai_indicators
from plagiarism_detector.reporting.page_allowance import compute_source_allowance
from app import versioning

logger = logging.getLogger(__name__)

# كاش الفهرس في الذاكرة لتسريع الفحوصات المتتالية
_CACHED_INDEX = None
_CACHED_REVIEW_HISTORY_INDEX = None
_CACHED_REVIEW_HISTORY_FINGERPRINT = ''


def _get_review_history_index(settings: dict) -> dict:
    """Build once per review-history state so scans do not re-embed old reports."""
    global _CACHED_REVIEW_HISTORY_INDEX, _CACHED_REVIEW_HISTORY_FINGERPRINT
    raw_segments = report_repo.get_review_history_segments(
        ('preliminary_accepted', 'rejected')
    )
    identity = '|'.join(
        f"{item.get('report_id')}:{item.get('review_status')}:{item.get('segment_number')}:{item.get('raw_text')}"
        for item in raw_segments
    )
    fingerprint = hashlib.sha256((
        identity
        + f"|shingle={settings.get('shingle_size', 4)}"
        + f"|semantic={bool(settings.get('enable_semantic_model', False))}"
    ).encode('utf-8')).hexdigest()
    if _CACHED_REVIEW_HISTORY_INDEX is None or fingerprint != _CACHED_REVIEW_HISTORY_FINGERPRINT:
        _CACHED_REVIEW_HISTORY_INDEX = build_review_history_index(raw_segments, settings)
        _CACHED_REVIEW_HISTORY_FINGERPRINT = fingerprint
    return _CACHED_REVIEW_HISTORY_INDEX


def build_pipeline_index(job_id: Optional[str] = None) -> dict:
    """
    بناء فهرس الاسترجاع السريع للمقاطع المرجعية من قاعدة البيانات ومزامنة حالته المؤسسية.
    الحالات: current, stale, building, failed
    """
    global _CACHED_INDEX
    from datetime import datetime
    from app.models.schema import IndexStateRecord
    from app.repositories.base_repo import get_session
    from app.services import audit_service, job_queue_service

    if job_id and job_queue_service.is_cancellation_requested(job_id):
        job_queue_service.finalize_cancellation(job_id)
        return _CACHED_INDEX or {}

    logger.info("جاري استخراج المقاطع وبناء فهرس الفحص الأكاديمي...")

    # 1. تسجيل حالة البدء في البناء (building)
    corpus_version = ''
    corpus_fingerprint = ''
    try:
        from app.services import corpus_governance_service
        c_info = corpus_governance_service.get_current_corpus_info()
        corpus_version = c_info.get('corpus_version', '')
        corpus_fingerprint = c_info.get('fingerprint', '')
    except Exception:
        pass

    with get_session() as session:
        idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
        if not idx_rec:
            idx_rec = IndexStateRecord(
                index_corpus_version=corpus_version,
                index_fingerprint=corpus_fingerprint,
                state='building',
                updated_at=datetime.utcnow()
            )
            session.add(idx_rec)
        else:
            idx_rec.state = 'building'
            idx_rec.index_corpus_version = corpus_version
            idx_rec.index_fingerprint = corpus_fingerprint
            idx_rec.updated_at = datetime.utcnow()
        session.commit()

    if job_id:
        job_queue_service.update_job_progress(job_id, 25, "جاري استخراج المقاطع المرجعية...")

    try:
        raw_segments = document_repo.get_all_segments_for_index()

        if job_id and job_queue_service.is_cancellation_requested(job_id):
            job_queue_service.finalize_cancellation(job_id)
            return _CACHED_INDEX or {}

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

            retriever.add_segment(idx, words_light, shingles, norm_light=n_light)

            corpus_shingles.append(shingles)
            corpus_light_texts.append(n_light)
            corpus_aggr_texts.append(n_aggr)
            corpus_metadata.append({
                'doc_id': seg['doc_id'],
                'reference_id': seg.get('reference_id', ''),
                'segment_number': seg.get('segment_number'),
                'title': seg['title'],
                'author': seg.get('author', ''),
                'page_number': seg.get('page_number'),  # رقم الصفحة المصدرية الحقيقي
                'raw_text': raw_text
            })

        if job_id:
            job_queue_service.update_job_progress(job_id, 75, "جاري تهيئة مصفوفة TF-IDF والفهارس المعجمية...")

        # بناء مصفوفة TF-IDF مسبقة للمقاطع إن وجدت نصوص
        vectorizer = None
        tfidf_matrix = None
        if corpus_light_texts:
            try:
                vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
                tfidf_matrix = vectorizer.fit_transform(corpus_light_texts)
            except Exception as e:
                logger.debug(f"تخطي بناء مصفوفة TF-IDF الشاملة: {e}")

        corpus_embeddings = None
        try:
            from app.services.settings_service import get_current_settings
            semantic_enabled = bool(get_current_settings().get('enable_semantic_model', False))
            if semantic_enabled and check_semantic_model_availability().get('available'):
                if job_id:
                    job_queue_service.update_job_progress(job_id, 85, "جاري بناء الفهرس الدلالي العربي والإنجليزي...")
                semantic_identity = '|'.join((
                    config.SEMANTIC_MODEL_NAME,
                    corpus_fingerprint or corpus_version,
                    str(len(corpus_light_texts)),
                ))
                cache_key = hashlib.sha256(semantic_identity.encode('utf-8')).hexdigest()[:24]
                cache_path = config.SEMANTIC_CACHE_DIR / f'{cache_key}.npy'
                if cache_path.is_file():
                    import numpy as np
                    cached = np.load(cache_path, allow_pickle=False)
                    if cached.ndim == 2 and cached.shape[0] == len(corpus_light_texts):
                        corpus_embeddings = cached
                if corpus_embeddings is None:
                    corpus_embeddings = compute_embeddings(corpus_light_texts)
                    if corpus_embeddings is not None:
                        temp_path = cache_path.with_suffix('.tmp.npy')
                        import numpy as np
                        np.save(temp_path, corpus_embeddings, allow_pickle=False)
                        os.replace(temp_path, cache_path)
        except Exception as e:
            logger.warning(f"تعذر بناء الفهرس الدلالي؛ سيستمر الفحص المعجمي: {e}")

        index_data = {
            'shingle_size': shingle_size,
            'retriever': retriever,
            'corpus_shingles': corpus_shingles,
            'corpus_light_texts': corpus_light_texts,
            'corpus_aggr_texts': corpus_aggr_texts,
            'corpus_metadata': corpus_metadata,
            'vectorizer': vectorizer,
            'tfidf_matrix': tfidf_matrix,
            'corpus_embeddings': corpus_embeddings,
            'total_segments': len(raw_segments),
            'index_corpus_version': corpus_version,
            'index_fingerprint': corpus_fingerprint,
            'built_at': datetime.utcnow()
        }

        if job_id and job_queue_service.is_cancellation_requested(job_id):
            job_queue_service.finalize_cancellation(job_id)
            return _CACHED_INDEX or {}

        # 2. تسجيل نجاح البناء (current) وترقية الفهرس ذرياً
        with get_session() as session:
            idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
            if idx_rec:
                idx_rec.state = 'current'
                idx_rec.index_corpus_version = corpus_version
                idx_rec.index_fingerprint = corpus_fingerprint
                idx_rec.built_at = datetime.utcnow()
                idx_rec.total_segments = len(raw_segments)
                idx_rec.error_message = ''
                idx_rec.updated_at = datetime.utcnow()
            session.commit()

        _CACHED_INDEX = index_data
        logger.info(f"تم بناء وتحديث الفهرس بنجاح: {len(raw_segments)} مقطع مرجعي (الإصدار: {corpus_version}).")

        if job_id:
            job_queue_service.complete_job(job_id, result={"total_segments": len(raw_segments), "corpus_version": corpus_version})

        try:
            audit_service.record_event(
                action="reference.index_rebuilt",
                category="reference",
                object_type="index_state",
                object_id=corpus_version or "latest",
                success=True,
                metadata={"total_segments": len(raw_segments), "fingerprint": corpus_fingerprint}
            )
        except Exception:
            pass

        return index_data

    except Exception as e:
        logger.error(f"فشل بناء فهرس الاسترجاع: {e}", exc_info=True)
        if job_id:
            from app.errors.error_codes import ErrorCode
            job_queue_service.fail_job(job_id, error_code=ErrorCode.CORPUS_INDEX_BUILD_FAILED, error_message=str(e))

        with get_session() as session:
            idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
            if idx_rec:
                idx_rec.state = 'failed'
                idx_rec.error_message = str(e)[:500]
                idx_rec.updated_at = datetime.utcnow()
            session.commit()
        raise e


def trigger_async_index_rebuild(target_corpus_version: Optional[str] = None, requested_by: str = 'system') -> str:
    """
    جدولة إعادة بناء الفهرس في الخلفية مع منع التكرار لنفس إصدار قاعدة المراجع.
    """
    from app.services import job_queue_service
    from app.services.job_queue_service import JobType
    from concurrent.futures import ThreadPoolExecutor

    job_id, err = job_queue_service.enqueue_job(
        job_type=JobType.REFERENCE_INDEX_REBUILD,
        target_corpus_version=target_corpus_version,
        requested_by=requested_by,
        payload={'target_corpus_version': target_corpus_version}
    )

    if job_id:
        def _run():
            try:
                build_pipeline_index(job_id=job_id)
            except Exception as e:
                logger.error(f"خطأ أثناء تشغيل بناء الفهرس غير المتزامن {job_id}: {e}")

        ThreadPoolExecutor(max_workers=1).submit(_run)

    return job_id or ''


def get_pipeline_index(auto_rebuild_if_stale: bool = True, shingle_size: Optional[int] = None) -> dict:
    """استرجاع الفهرس المخزن في الذاكرة مع التحقق من عدم تقادمه (Staleness Protection)."""
    global _CACHED_INDEX
    from app.models.schema import IndexStateRecord
    from app.repositories.base_repo import get_session

    is_stale = False
    if _CACHED_INDEX is None:
        is_stale = True
    else:
        try:
            with get_session() as session:
                idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
                if idx_rec and idx_rec.state in ('stale', 'failed'):
                    is_stale = True
        except Exception:
            pass

    if is_stale:
        if auto_rebuild_if_stale:
            _CACHED_INDEX = build_pipeline_index()
        else:
            raise RuntimeError("فهرس الاسترجاع غير متطابق مع قاعدة المراجع الحالية (CORPUS_INDEX_STALE)")

    index = _CACHED_INDEX
    if shingle_size is None or index.get('shingle_size') == shingle_size:
        return index

    # A scan-local view prevents different concurrent scan settings from
    # modifying the shared corpus cache or another scan's retriever.
    retriever = CandidateRetriever()
    shingles = []
    for idx, (light, aggressive) in enumerate(zip(
        index['corpus_light_texts'], index['corpus_aggr_texts']
    )):
        value = get_shingles(aggressive, size=shingle_size)
        shingles.append(value)
        retriever.add_segment(idx, light.split(), value, norm_light=light)
    return dict(index, retriever=retriever, corpus_shingles=shingles,
                shingle_size=shingle_size)


def invalidate_pipeline_index(mark_stale_in_db: bool = True):
    """إلغاء الفهرس المؤقت وإعلانه كـ stale في قاعدة البيانات."""
    global _CACHED_INDEX
    _CACHED_INDEX = None
    if mark_stale_in_db:
        from datetime import datetime
        from app.models.schema import IndexStateRecord
        from app.repositories.base_repo import get_session
        try:
            with get_session() as session:
                idx_rec = session.query(IndexStateRecord).order_by(IndexStateRecord.id.desc()).first()
                if idx_rec:
                    idx_rec.state = 'stale'
                    idx_rec.updated_at = datetime.utcnow()
                    session.commit()
        except Exception:
            pass


def analyze_academic_document(
    raw_text: str,
    pages_data: Optional[list[dict]] = None,
    settings_override: Optional[dict] = None,
    exact_reference_match: Optional[dict] = None,
    excluded_doc_ids: Optional[set[int]] = None
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

    index_data = get_pipeline_index(shingle_size=settings['shingle_size'])
    retriever: CandidateRetriever = index_data['retriever']
    corpus_shingles = index_data['corpus_shingles']
    corpus_light_texts = index_data['corpus_light_texts']
    corpus_aggr_texts = index_data['corpus_aggr_texts']
    corpus_metadata = index_data['corpus_metadata']
    vectorizer = index_data['vectorizer']
    tfidf_matrix = index_data['tfidf_matrix']
    corpus_embeddings = index_data.get('corpus_embeddings')

    review_history_index = _get_review_history_index(settings)

    semantic_query_embeddings = None
    if settings.get('enable_semantic_model', False) and (
        corpus_embeddings is not None or review_history_index.get('embeddings') is not None
    ):
        semantic_query_embeddings = compute_embeddings([seg.raw_text for seg in segments_list])

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

    # These settings also belong to the report snapshot when extraction yields
    # no analysable segments.  Initialise them before the loop so an empty or
    # image-only document produces a valid zero-evidence report instead of an
    # UnboundLocalError while building the response.
    citation_mode = settings.get('citation_filter_mode', 'refined')
    common_mode = settings.get('common_text_filter_mode', 'span_level')
    retrieval_mode = settings.get('candidate_retrieval_mode', 'dual_channel')

    for segment_index, seg in enumerate(segments_list):
        w_count = seg.word_count
        total_words += w_count

        seg_dict = {
            'text': seg.raw_text,
            'page_number': seg.page_number,
            'source_file': seg.source_file,
            'file_index': seg.file_index,
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

        # 0. فحص واستبعاد النصوص المؤسسية الشائعة على مستوى المقاطع (EXP-03)
        substantive_text, has_common, extracted_spans = filter_common_spans(
            seg.raw_text,
            min_substantive_words=settings.get('min_sentence_words', 4),
            mode=common_mode
        )

        if has_common and not substantive_text.strip():
            seg_dict['status'] = 'suppressed'
            seg_dict['match_type'] = 'COMMON TEXT'
            seg_dict['is_common_phrase'] = True
            seg_dict['common_spans'] = extracted_spans
            processed_segments.append(seg_dict)
            continue

        if has_common and substantive_text.strip():
            seg_dict['has_common_preamble'] = True
            seg_dict['common_spans'] = extracted_spans
            eval_aggr = normalize_aggressive(substantive_text)
            eval_light = normalize_light(substantive_text)
        else:
            eval_aggr = seg.normalized_aggressive
            eval_light = seg.normalized_light

        # فحص وجود استشهاد أو علامات تنصيص (EXP-04)
        citation_check = detect_citation(seg.raw_text, mode=citation_mode)
        if citation_check.is_cited:
            seg_dict['is_cited'] = True
            seg_dict['citation_detail'] = citation_check.citation_detail

        # ── المرحلة A: كشف النسخ الحرفي عبر Shingles + Jaccard ───
        q_shingles = get_shingles(eval_aggr, size=settings['shingle_size'])
        shingle_candidates = retriever.retrieve_candidates_for_shingles(q_shingles)
        if excluded_doc_ids:
            shingle_candidates = [idx for idx in shingle_candidates
                                  if corpus_metadata[idx]['doc_id'] not in excluded_doc_ids]

        match_found = False

        if shingle_candidates:
            res_a = match_exact_or_near_copy(
                query_shingles=q_shingles,
                query_norm_text=eval_aggr,
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
                seg_dict['source_reference_id'] = meta.get('reference_id', '')
                seg_dict['source_segment_number'] = meta.get('segment_number')
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

        # ── المرحلة B: كشف إعادة الصياغة عبر TF-IDF و الاسترجاع المطور (EXP-01) ──
        if not match_found:
            token_candidates = retriever.retrieve_candidates(
                eval_light,
                top_k=settings['max_candidate_retrieval'],
                mode=retrieval_mode
            )
            if excluded_doc_ids:
                token_candidates = [
                    cand_idx for cand_idx in token_candidates
                    if corpus_metadata[cand_idx]['doc_id'] not in excluded_doc_ids
                ]
            if token_candidates:
                res_b = match_lexical_paraphrase(
                    query_norm_text=eval_light,
                    candidate_indices=token_candidates,
                    corpus_norm_texts=corpus_light_texts,
                    threshold=settings['tfidf_threshold'],
                    vectorizer=vectorizer,
                    corpus_tfidf_matrix=tfidf_matrix
                )
                if res_b:
                    cand_idx, score, m_type = res_b
                    meta = corpus_metadata[cand_idx]
                    if not accept_lexical_paraphrase(
                        substantive_text or seg.raw_text,
                        meta['raw_text'],
                    ):
                        res_b = None

                if res_b:
                    cand_idx, score, m_type = res_b
                    meta = corpus_metadata[cand_idx]
                    doc_id = meta['doc_id']
                    p_score = min(round(score * 100), 100)

                    seg_dict['source_id'] = doc_id
                    seg_dict['source_reference_id'] = meta.get('reference_id', '')
                    seg_dict['source_segment_number'] = meta.get('segment_number')
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
        if (
            not match_found
            and settings.get('enable_semantic_model', False)
            and semantic_query_embeddings is not None
            and corpus_embeddings is not None
        ):
            semantic_candidates = [
                idx for idx, meta in enumerate(corpus_metadata)
                if not excluded_doc_ids or meta['doc_id'] not in excluded_doc_ids
            ]
            res_c = match_semantic_similarity(
                query_text=seg.raw_text,
                candidate_indices=semantic_candidates,
                corpus_texts=corpus_light_texts,
                corpus_embeddings=corpus_embeddings,
                threshold=settings['semantic_threshold'],
                query_embedding=semantic_query_embeddings[segment_index],
            )
            if res_c:
                cand_idx, score, _match_type = res_c
                meta = corpus_metadata[cand_idx]
                if not accept_semantic_paraphrase(
                    substantive_text or seg.raw_text,
                    meta['raw_text'],
                    score,
                    settings['semantic_threshold'],
                ):
                    res_c = None

            if res_c:
                cand_idx, score, _match_type = res_c
                meta = corpus_metadata[cand_idx]
                doc_id = meta['doc_id']
                seg_dict.update({
                    'source_id': doc_id,
                    'source_reference_id': meta.get('reference_id', ''),
                    'source_segment_number': meta.get('segment_number'),
                    'source_title': meta['title'],
                    'source_author': meta['author'],
                    'source_page': meta['page_number'],
                    'source_page_display': f"ص. {meta['page_number']}" if meta['page_number'] else "غير متاح",
                    'matched_text': meta['raw_text'],
                    'score': score,
                    'pct': min(round(score * 100), 100),
                    'status': 'cited' if seg_dict['is_cited'] else 'paraphrased',
                    'match_type': 'CITED SEMANTIC MATCH' if seg_dict['is_cited'] else 'SEMANTIC PARAPHRASE',
                })
                words_by_source[doc_id] += w_count
                pages_by_source[doc_id].add(meta['page_number'])
                source_info[doc_id] = {'title': meta['title'], 'author': meta['author']}

        # ── سجل القبول المبدئي: يدخل في النسبة الأكاديمية الأساسية ──
        history_query_embedding = (
            semantic_query_embeddings[segment_index]
            if semantic_query_embeddings is not None else None
        )
        preliminary_match = match_review_history_segment(
            substantive_text or seg.raw_text,
            review_history_index,
            settings,
            {'preliminary_accepted'},
            history_query_embedding,
        )
        if preliminary_match and float(preliminary_match[1]) > float(seg_dict.get('score') or 0):
            meta, score, history_match_type = preliminary_match
            source_key = f"review:{meta['report_id']}"
            is_direct = history_match_type in ('DIRECT COPY', 'NEAR COPY')
            seg_dict.update({
                'source_id': None,
                'source_key': source_key,
                'source_report_id': meta['report_id'],
                'source_review_status': 'preliminary_accepted',
                'source_reference_id': '',
                'source_segment_number': meta.get('segment_number'),
                'source_title': meta['title'],
                'source_author': meta.get('author', ''),
                'source_page': meta.get('page_number'),
                'source_page_display': f"ص. {meta['page_number']}" if meta.get('page_number') else 'غير متاح',
                'matched_text': meta['raw_text'],
                'score': score,
                'pct': min(round(score * 100), 100),
                'status': 'cited' if seg_dict['is_cited'] else ('copied' if is_direct else 'paraphrased'),
                'match_type': (
                    'CITED MATCH' if seg_dict['is_cited'] else
                    ('DIRECT COPY' if is_direct else history_match_type)
                ),
            })
            source_info[source_key] = {
                'title': meta['title'],
                'author': meta.get('author', ''),
            }

        # ── سجل المرفوضات: تنبيه إعادة تقديم مستقل لا يرفع النسبة الرسمية ──
        rejected_match = match_review_history_segment(
            substantive_text or seg.raw_text,
            review_history_index,
            settings,
            {'rejected'},
            history_query_embedding,
        )
        if rejected_match:
            meta, score, history_match_type = rejected_match
            seg_dict['rejected_history_match'] = {
                'report_id': meta['report_id'],
                'research_id': meta.get('research_id'),
                'title': meta['title'],
                'author': meta.get('author', ''),
                'page_number': meta.get('page_number'),
                'segment_number': meta.get('segment_number'),
                'matched_text': meta['raw_text'],
                'score': score,
                'pct': min(round(score * 100), 100),
                'match_type': history_match_type,
            }

        processed_segments.append(seg_dict)

    # 4. فحص واستبعاد أقسام المراجع الببليوغرافية
    processed_segments, bib_count = filter_bibliography_sections(processed_segments)

    # 5. حساب الإجماليات بدقة رياضية بعد استبعاد المراجع الببليوغرافية
    copied_words = 0
    para_words = 0
    cited_words = 0
    problematic_words = 0
    rejected_history_words = 0
    clean_total_words = 0
    rejected_history_sources: dict[str, dict] = {}

    # إعادة بناء إحصائيات المصادر بعد استبعاد Bibliography لضمان توافق نسب المصادر مع overall_pct
    words_by_source_clean: dict[int, int] = defaultdict(int)
    pages_by_source_clean: dict[int, set] = defaultdict(set)

    for seg in processed_segments:
        w_cnt = len(seg['text'].split())

        if seg.get('is_bibliography'):
            # استبعاد فقرات المراجع من البسط والمقام معاً لتفادي تضخم النسب
            continue

        clean_total_words += w_cnt

        if seg['status'] == 'copied':
            copied_words += w_cnt
            problematic_words += w_cnt
        elif seg['status'] == 'paraphrased':
            para_words += w_cnt
            problematic_words += w_cnt
        elif seg['status'] == 'cited':
            cited_words += w_cnt

        rejected_match = seg.get('rejected_history_match')
        if rejected_match:
            rejected_history_words += w_cnt
            existing_rejected = rejected_history_sources.get(rejected_match['report_id'])
            if not existing_rejected or rejected_match.get('pct', 0) >= existing_rejected.get('max_pct', 0):
                rejected_history_sources[rejected_match['report_id']] = {
                    'report_id': rejected_match['report_id'],
                    'title': rejected_match.get('title', ''),
                    'author': rejected_match.get('author', ''),
                    'page_number': rejected_match.get('page_number'),
                    'matched_text': rejected_match.get('matched_text', ''),
                    'max_pct': rejected_match.get('pct', 0),
                }

        # إعادة تجميع كلمات المصادر من النص القابل للتحليل فقط
        source_key = seg.get('source_key') or seg.get('source_id')
        if source_key is not None and seg['status'] in ('copied', 'paraphrased', 'cited'):
            words_by_source_clean[source_key] += w_cnt
            pages_by_source_clean[source_key].add(seg.get('source_page'))

    total_safe_words = max(clean_total_words, 1)
    matched_total_words = copied_words + para_words + cited_words

    # ضمان النسب الرياضية الدقيقة: 0 <= % <= 100 و problematic <= overall
    overall_pct = min(round((matched_total_words / total_safe_words) * 100, 1), 100.0)
    problematic_pct = min(round((problematic_words / total_safe_words) * 100, 1), overall_pct)
    copied_pct = min(round((copied_words / total_safe_words) * 100, 1), 100.0)
    paraphrase_pct = min(round((para_words / total_safe_words) * 100, 1), 100.0)
    cited_pct = min(round((cited_words / total_safe_words) * 100, 1), 100.0)
    rejected_history_pct = min(round((rejected_history_words / total_safe_words) * 100, 1), 100.0)

    # 6. تفاصيل المصادر ومنطق الصفحات المسموحة (Phase 8)
    sources_list = []
    exceeded_sources = []
    for s_id, s_words in words_by_source_clean.items():
        s_title = source_info[s_id]['title']
        s_author = source_info[s_id]['author']
        s_pages_set = pages_by_source_clean[s_id]

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
        'rejected_history_pct': rejected_history_pct,
        'rejected_history_words': rejected_history_words,
        'rejected_history_matches_count': sum(
            1 for segment in processed_segments if segment.get('rejected_history_match')
        ),
        'rejected_history_sources': sorted(
            rejected_history_sources.values(),
            key=lambda item: item.get('max_pct', 0),
            reverse=True,
        ),
        'total_words': total_words,
        'copied_words': copied_words,
        'paraphrased_words': para_words,
        'cited_words': cited_words,
        'problematic_words': problematic_words,
        'segments': processed_segments,
        'sources': sources_list,
        'cheating': cheating_res,
        'page_limit_alert': page_limit_alert,
        'bibliography_segments_count': bib_count,
        'application_version': versioning.APPLICATION_VERSION,
        'engine_version': versioning.ENGINE_VERSION,
        'detector_version': versioning.DETECTOR_VERSION,
        'citation_engine_version': versioning.CITATION_ENGINE_VERSION,
        'common_text_version': versioning.COMMON_TEXT_HANDLING_VERSION,
        'normalization_version': versioning.NORMALIZATION_VERSION,
        'candidate_retrieval_mode': retrieval_mode,
        'common_text_filter_mode': common_mode,
        'citation_filter_mode': citation_mode,
        'settings_snapshot': dict(settings)
        , 'exact_file_match': {
            'detected': bool(exact_reference_match),
            'method': 'sha256' if exact_reference_match else None
        }
    }
