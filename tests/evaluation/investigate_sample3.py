# -*- coding: utf-8 -*-
"""
تحليل معمّق للعينة sample_3 (PARAPHRASE → classified as ORIGINAL).
يطبع مقاييس التشابه التالية دون المساس بأي عتبة إنتاجية:
  - Jaccard Similarity (على shingles بحجم 4)
  - SequenceMatcher ratio
  - Word-level TF-IDF cosine similarity
  - Char-level TF-IDF cosine similarity (char_wb, 3-4 gram)
  - Semantic cosine similarity (فقط إن كان نموذج أوفلاين متاحاً فعلاً)
"""

import sys
import io
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from plagiarism_detector.preprocessing.normalizer import (
    normalize_aggressive, normalize_light, get_shingles
)
from plagiarism_detector.detection.shingle_matcher import jaccard_similarity
from plagiarism_detector.detection.semantic_matcher import (
    check_semantic_model_availability, compute_embeddings
)

# ─── النصوص ─────────────────────────────────────────────────────────────────
SOURCE = (
    "تسعى الدول المتقدمة إلى توظيف خوارزميات الذكاء الاصطناعي في تحليل "
    "البيانات الأمنية الضخمة للتنبؤ بالأنماط الإجرامية قبل وقوعها والحد من مخاطرها."
)
SUBMITTED = (
    "تهدف الحكومات الحديثة لاستخدام تقنيات تعلم الآلة لمعالجة تدفقات المعلومات "
    "الاستخباراتية وتوقع الجرائم المستقبلية لمكافحة التهديدات بفاعلية."
)

print("=" * 72)
print("  تحليل العينة sample_3: PARAPHRASE → صُنِّفت ORIGINAL")
print("=" * 72)
print(f"\n[المصدر]   : {SOURCE}")
print(f"[المُقدَّم] : {SUBMITTED}")

# ─── 1. Jaccard على shingles حجم 4 ──────────────────────────────────────────
src_aggr = normalize_aggressive(SOURCE)
sub_aggr = normalize_aggressive(SUBMITTED)

src_sh4 = get_shingles(src_aggr, size=4)
sub_sh4 = get_shingles(sub_aggr, size=4)
jaccard_4 = jaccard_similarity(src_sh4, sub_sh4)

src_sh3 = get_shingles(src_aggr, size=3)
sub_sh3 = get_shingles(sub_aggr, size=3)
jaccard_3 = jaccard_similarity(src_sh3, sub_sh3)

print(f"\n{'─'*72}")
print("1. Jaccard Similarity")
print(f"   Shingle size=4 : {jaccard_4:.4f}")
print(f"   Shingle size=3 : {jaccard_3:.4f}")
print(f"   [normalized aggressive] src: «{src_aggr}»")
print(f"   [normalized aggressive] sub: «{sub_aggr}»")

# ─── 2. SequenceMatcher ratio ─────────────────────────────────────────────────
seq_ratio_aggr = SequenceMatcher(None, src_aggr, sub_aggr).ratio()
src_light = normalize_light(SOURCE)
sub_light = normalize_light(SUBMITTED)
seq_ratio_light = SequenceMatcher(None, src_light, sub_light).ratio()

print(f"\n{'─'*72}")
print("2. SequenceMatcher ratio")
print(f"   On aggressive-normalized text : {seq_ratio_aggr:.4f}")
print(f"   On light-normalized text      : {seq_ratio_light:.4f}")

# ─── 3. Word-level TF-IDF cosine similarity ──────────────────────────────────
texts = [src_light, sub_light]
word_vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
wmat = word_vec.fit_transform(texts)
word_cos = float(cosine_similarity(wmat[0:1], wmat[1:2])[0][0])

word_vec_1 = TfidfVectorizer(ngram_range=(1, 1), sublinear_tf=True, min_df=1)
wmat_1 = word_vec_1.fit_transform(texts)
word_cos_1 = float(cosine_similarity(wmat_1[0:1], wmat_1[1:2])[0][0])

print(f"\n{'─'*72}")
print("3. Word-level TF-IDF cosine similarity  (light-normalised)")
print(f"   Unigrams (1-1)  : {word_cos_1:.4f}")
print(f"   Unigrams+bigrams (1-2) : {word_cos:.4f}")

# ─── 4. Char-level TF-IDF cosine similarity ──────────────────────────────────
char_vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(3, 4), min_df=1)
cmat = char_vec.fit_transform(texts)
char_cos = float(cosine_similarity(cmat[0:1], cmat[1:2])[0][0])

char_vec2 = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 3), min_df=1)
cmat2 = char_vec2.fit_transform(texts)
char_cos2 = float(cosine_similarity(cmat2[0:1], cmat2[1:2])[0][0])

print(f"\n{'─'*72}")
print("4. Char-level TF-IDF cosine similarity  (light-normalised)")
print(f"   char_wb 3-4 gram : {char_cos:.4f}")
print(f"   char_wb 2-3 gram : {char_cos2:.4f}")

# ─── 5. blended score (same formula as tfidf_matcher) ────────────────────────
blended = max(word_cos, 0.7 * word_cos + 0.3 * char_cos)
print(f"\n{'─'*72}")
print("5. Blended score (same formula used in tfidf_matcher.py)")
print(f"   max(word_cos, 0.7*word_cos + 0.3*char_cos) = {blended:.4f}")
print(f"   Production threshold in evaluate_system.py  = 0.20")
print(f"   → Would pass threshold 0.20? {'YES ✅' if blended >= 0.20 else 'NO ❌'}")
print(f"   → Would pass threshold 0.15? {'YES ✅' if blended >= 0.15 else 'NO ❌'}")
print(f"   → Would pass threshold 0.10? {'YES ✅' if blended >= 0.10 else 'NO ❌'}")

# ─── 6. Semantic similarity (only if local model verified available) ───────────
print(f"\n{'─'*72}")
print("6. Semantic cosine similarity (offline local model only)")
avail = check_semantic_model_availability()
if avail['available']:
    embs = compute_embeddings([SOURCE, SUBMITTED])
    if embs is not None and len(embs) == 2:
        v1, v2 = embs[0], embs[1]
        n1 = (v1 @ v2) / (
            (sum(x**2 for x in v1)**0.5) * (sum(x**2 for x in v2)**0.5) + 1e-10
        )
        import numpy as np
        sem_cos = float(
            (v1 @ v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-10)
        )
        print(f"   Semantic cosine similarity : {sem_cos:.4f}")
    else:
        print("   فشل حساب التضمين رغم توفر النموذج.")
else:
    print(f"   ⚠ النموذج الدلالي غير متاح محلياً → تم تخطي الحساب الدلالي.")
    print(f"   السبب: {avail['reason']}")

# ─── 7. Diagnosis ─────────────────────────────────────────────────────────────
print(f"\n{'═'*72}")
print("الخلاصة التشخيصية:")
print(f"  • Jaccard(4)  = {jaccard_4:.4f} — منخفض جداً (لا توجد shingles مشتركة بحجم 4)")
print(f"  • Seq ratio   = {seq_ratio_light:.4f} — منخفض (الجمل مختلفة بنيوياً)")
print(f"  • TF-IDF word = {word_cos:.4f} — متوسط-منخفض (المفردات مختلفة إلى حد بعيد)")
print(f"  • TF-IDF char = {char_cos:.4f} — متوسط (تشارك بعض التراكيب المورفولوجية)")
print(f"  • Blended     = {blended:.4f} — {'يتخطى' if blended >= 0.20 else 'لا يتخطى'} عتبة 0.20")
print()
print("  السبب الجذري لتصنيف sample_3 كـ ORIGINAL:")
print("  ─────────────────────────────────────────")
print("  العينة هي paraphrase دلالية حقيقية لكنها تستخدم:")
print("    (أ) مفردات مختلفة تماماً (الدول المتقدمة → الحكومات الحديثة)")
print("    (ب) خوارزميات الذكاء الاصطناعي → تقنيات تعلم الآلة")
print("    (ج) تحليل البيانات الأمنية → معالجة تدفقات المعلومات الاستخباراتية")
print("    (د) بنية جملة مختلفة كلياً مع حفاظ على المعنى")
print("  هذا يعني أن TF-IDF اللفظي لا يكفي وحده لكشف هذا النوع من إعادة الصياغة")
print("  بدون نموذج دلالي (semantic embedding) أوفلاين.")
print("=" * 72)
