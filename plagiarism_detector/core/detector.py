# -*- coding: utf-8 -*-
"""
محرك الكشف الرئيسي:
1. بناء الفهرس من كل الأبحاث المخزنة (مرة واحدة، ويتحدث تلقائيًا)
2. كشف النسخ الحرفي → shingles + Jaccard similarity (على مستوى المتواليات)
3. كشف إعادة الصياغة → TF-IDF + Cosine similarity (على مستوى الجملة)
4. إرجاع تقرير مفصل جاهز للعرض في الواجهة
"""

import logging
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .normalize import normalize_arabic, split_sentences, get_shingles
from . import db

logger = logging.getLogger(__name__)

# ============================================================
# إعدادات قابلة للتعديل
# ============================================================
SHINGLE_SIZE           = 5      # عدد الكلمات في كل shingle (تتابع الكلمات)
JACCARD_COPY_THRESHOLD = 0.40   # نسبة Jaccard فوقها → نسخ حرفي
COSINE_PARA_THRESHOLD  = 0.60   # نسبة Cosine فوقها → إعادة صياغة
MIN_SENTENCE_WORDS     = 4      # تجاهل الجمل الأقصر من 4 كلمات فقط


# ============================================================
# بناء الفهرس
# ============================================================
def build_index() -> dict:
    """
    يبني فهرسًا على مستوى الجملة والمتواليات من كل الأبحاث في قاعدة البيانات.
    الفهرس يُخزَّن على القرص ويُحمَّل تلقائيًا في الفحوصات اللاحقة.
    """
    logger.info("جاري بناء الفهرس...")
    papers = db.get_all_papers_full()

    sent_texts     = []   # النص المطبَّع لكل جملة
    sent_originals = []   # النص الأصلي لكل جملة
    sent_paper_ids = []   # رقم البحث المصدر لكل جملة
    sent_shingles_list = []  # shingles لكل جملة (list of sets)

    shingle_index: dict[tuple, set[int]] = defaultdict(set)

    for paper in papers:
        pid = paper['id']
        for sent in split_sentences(paper['full_text'], min_words=MIN_SENTENCE_WORDS):
            norm = normalize_arabic(sent)
            if len(norm.split()) < MIN_SENTENCE_WORDS:
                continue
            idx = len(sent_texts)
            sent_texts.append(norm)
            sent_originals.append(sent)
            sent_paper_ids.append(pid)

            shingles = get_shingles(norm, SHINGLE_SIZE)
            sent_shingles_list.append(shingles)
            for sh in shingles:
                shingle_index[sh].add(idx)

    vectorizer   = None
    tfidf_matrix = None
    if sent_texts:
        vectorizer   = TfidfVectorizer(min_df=1, sublinear_tf=True)
        tfidf_matrix = vectorizer.fit_transform(sent_texts)

    index_obj = {
        'shingle_index'     : dict(shingle_index),
        'sent_shingles_list': sent_shingles_list,
        'sent_texts'        : sent_texts,
        'sent_originals'    : sent_originals,
        'sent_paper_ids'    : sent_paper_ids,
        'paper_titles'      : {p['id']: p['title'] for p in papers},
        'paper_authors'     : {p['id']: p.get('author', '') for p in papers},
        'vectorizer'        : vectorizer,
        'tfidf_matrix'      : tfidf_matrix,
    }
    db.save_index(index_obj)
    logger.info(f"تم بناء الفهرس: {len(papers)} بحث، {len(sent_texts)} جملة.")
    return index_obj


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ============================================================
# التحليل الرئيسي
# ============================================================
def analyze_text(raw_text: str) -> dict:
    """
    يحلل نص بحث جديد ويرجع تقرير مفصل:
    يقوم بحساب نسبة الاقتباس الحقيقية لكل مصدر بناءً على مجموع الكلمات المتطابقة
    في الجمل والمتواليات من ذلك المصدر بدلاً من أخذ أعلى قيمة جملة منفردة.
    """
    index_obj = db.load_index()
    if index_obj is None:
        index_obj = build_index()

    shingle_index      = index_obj['shingle_index']
    sent_shingles_list = index_obj['sent_shingles_list']
    sent_paper_ids     = index_obj['sent_paper_ids']
    paper_titles       = index_obj['paper_titles']
    paper_authors      = index_obj.get('paper_authors', {})
    vectorizer         = index_obj['vectorizer']
    tfidf_matrix       = index_obj['tfidf_matrix']

    sentences = split_sentences(raw_text, min_words=MIN_SENTENCE_WORDS)

    segments          = []
    total_words       = 0
    copied_words      = 0
    paraphrased_words = 0
    words_per_source: dict[int, int] = defaultdict(int)

    for sent in sentences:
        norm = normalize_arabic(sent)
        nw = len(norm.split())
        total_words += max(nw, len(sent.split()))

        if nw < MIN_SENTENCE_WORDS:
            segments.append({'text': sent, 'status': 'original'})
            continue

        # ==== خطوة 1: كشف النسخ الحرفي ====
        q_shingles = get_shingles(norm, SHINGLE_SIZE)

        candidate_idxs: set[int] = set()
        for sh in q_shingles:
            candidate_idxs |= shingle_index.get(sh, set())

        best_copy_score = 0.0
        best_copy_idx   = -1
        for cidx in candidate_idxs:
            score = _jaccard(q_shingles, sent_shingles_list[cidx])
            if score > best_copy_score:
                best_copy_score = score
                best_copy_idx   = cidx

        if best_copy_score >= JACCARD_COPY_THRESHOLD:
            pid = sent_paper_ids[best_copy_idx]
            pct = min(round(best_copy_score * 100), 100)
            words_per_source[pid] += nw
            copied_words += nw
            segments.append({
                'text'          : sent,
                'status'        : 'copied',
                'source_id'     : pid,
                'source_title'  : paper_titles.get(pid, 'مصدر غير معروف'),
                'source_author' : paper_authors.get(pid, 'غير محدد'),
                'source_text'   : index_obj['sent_originals'][best_copy_idx] if best_copy_idx < len(index_obj['sent_originals']) else '',
                'match_pct'     : pct,
            })
            continue

        # ==== خطوة 2: كشف إعادة الصياغة (TF-IDF Cosine) ====
        if vectorizer is not None and tfidf_matrix is not None and tfidf_matrix.shape[0] > 0:
            try:
                q_vec   = vectorizer.transform([norm])
                sims    = cosine_similarity(q_vec, tfidf_matrix)[0]
                best_idx  = int(np.argmax(sims))
                best_sim  = float(sims[best_idx])
            except Exception:
                best_sim = 0.0
                best_idx = -1

            if best_sim >= COSINE_PARA_THRESHOLD:
                pid = sent_paper_ids[best_idx]
                pct = min(round(best_sim * 100), 100)
                words_per_source[pid] += nw
                paraphrased_words += nw
                segments.append({
                    'text'          : sent,
                    'status'        : 'paraphrased',
                    'source_id'     : pid,
                    'source_title'  : paper_titles.get(pid, 'مصدر غير معروف'),
                    'source_author' : paper_authors.get(pid, 'غير محدد'),
                    'source_text'   : index_obj['sent_originals'][best_idx] if best_idx < len(index_obj['sent_originals']) else '',
                    'match_pct'     : pct,
                })
                continue

        segments.append({'text': sent, 'status': 'original'})

    # ---- النسب الإجمالية والمصادر وتتبع الحد الأقصى للصفحات ----
    total_words      = max(total_words, 1)
    copied_pct       = round(copied_words      / total_words * 100, 1)
    paraphrase_pct   = round(paraphrased_words / total_words * 100, 1)
    overall_pct      = round(copied_pct + paraphrase_pct, 1)

    # معيار حجم الصفحة الأكاديمية القياسية (250 كلمة لكل صفحة) والحد الأقصى المسموح (5 صفحات)
    WORDS_PER_PAGE = 250
    MAX_ALLOWED_PAGES = 5.0

    sources_list = []
    exceeded_sources = []

    for pid, src_words in words_per_source.items():
        src_pct = round((src_words / total_words) * 100, 1)
        est_pages = round(src_words / WORDS_PER_PAGE, 1)
        
        src_entry = {
            'paper_id' : pid,
            'title'    : paper_titles.get(pid, 'مصدر غير معروف'),
            'author'   : paper_authors.get(pid, 'غير محدد'),
            'words'    : src_words,
            'pages'    : est_pages,
            'pct'      : src_pct
        }

        if est_pages >= MAX_ALLOWED_PAGES:
            exceeded_sources.append(src_entry)

        if src_pct > 0:
            sources_list.append(src_entry)

    sources_list = sorted(sources_list, key=lambda x: -x['pct'])

    page_limit_alert = {
        'has_limit_exceeded': len(exceeded_sources) > 0,
        'max_allowed_pages' : MAX_ALLOWED_PAGES,
        'exceeded_sources'  : exceeded_sources,
        'details'           : [
            f"تم اقتباس ما يعادل {s['pages']} صفحة تقريباً ({s['words']:,} كلمة) من المرجع: «{s['title']}» للمؤلف ({s['author']})، متجاوزاً الحد الأقصى المسموح للاقتباس من مصدر واحد ({int(MAX_ALLOWED_PAGES)} صفحات)."
            for s in exceeded_sources
        ]
    }

    # إسناد إجمالي عدد الصفحات والكلمات للمصدر داخل كل مقطع مظلل
    for seg in segments:
        if 'source_id' in seg and seg['source_id'] in words_per_source:
            s_words = words_per_source[seg['source_id']]
            seg['source_words'] = s_words
            seg['source_pages'] = round(s_words / WORDS_PER_PAGE, 1)

    total_pages = round(total_words / WORDS_PER_PAGE, 1)
    copied_pages = round(copied_words / WORDS_PER_PAGE, 1)
    paraphrase_pages = round(paraphrased_words / WORDS_PER_PAGE, 1)
    plagiarized_pages = round((copied_words + paraphrased_words) / WORDS_PER_PAGE, 1)

    return {
        'segments'          : segments,
        'overall_pct'       : overall_pct,
        'copied_pct'        : copied_pct,
        'paraphrase_pct'    : paraphrase_pct,
        'sources'           : sources_list,
        'total_sentences'   : len(sentences),
        'total_words'       : total_words,
        'total_pages'       : total_pages,
        'copied_words'      : copied_words,
        'copied_pages'      : copied_pages,
        'paraphrase_words'  : paraphrased_words,
        'paraphrase_pages'  : paraphrase_pages,
        'plagiarized_words' : copied_words + paraphrased_words,
        'plagiarized_pages' : plagiarized_pages,
        'page_limit_alert'  : page_limit_alert,
    }


