import numpy as np

import config
from plagiarism_detector.detection import semantic_matcher


class _RecordingEmbedder:
    def __init__(self):
        self.seen = []

    def embed(self, texts, batch_size):
        self.seen.extend(texts)
        for _text in texts:
            yield np.array([1.0, 0.0], dtype=np.float32)


def test_e5_role_prefixes_are_applied(monkeypatch):
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(semantic_matcher, 'get_embedder', lambda: embedder)

    semantic_matcher.compute_embeddings(['سؤال عربي'], role='query')
    semantic_matcher.compute_embeddings(['مرجع عربي'], role='passage')

    assert embedder.seen == ['query: سؤال عربي', 'passage: مرجع عربي']


def test_e5_prefix_is_not_duplicated(monkeypatch):
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(semantic_matcher, 'get_embedder', lambda: embedder)

    semantic_matcher.compute_embeddings(['query: نص جاهز'], role='query')

    assert embedder.seen == ['query: نص جاهز']


def test_invalid_embedding_role_fails_closed(monkeypatch):
    embedder = _RecordingEmbedder()
    monkeypatch.setattr(semantic_matcher, 'get_embedder', lambda: embedder)

    assert semantic_matcher.compute_embeddings(['نص'], role='invalid') is None
    assert embedder.seen == []


def test_bundled_e5_model_is_complete_and_offline():
    availability = semantic_matcher.check_semantic_model_availability()

    assert availability['available'] is True
    assert availability['identifier'] == 'intfloat/multilingual-e5-small'
    assert availability['offline'] is True
    assert config.SEMANTIC_MODEL_FILE.endswith('model_qint8_generic.onnx')


def test_bundled_e5_separates_arabic_paraphrase_from_unrelated_text():
    query = (
        'إدارة الأزمات في المطارات تتطلب خططا استباقية وتنسيقا بين الجهات '
        'الأمنية لضمان سلامة المسافرين واستمرار التشغيل'
    )
    paraphrase = (
        'يساعد التخطيط المسبق والتعاون بين الأجهزة المختصة على مواجهة أزمات '
        'المطارات وحماية الركاب واستدامة العمل'
    )
    unrelated = (
        'تعتمد الزراعة الحديثة على نظم الري بالتنقيط والأسمدة العضوية لزيادة '
        'إنتاج المحاصيل في الأراضي الصحراوية'
    )

    query_embedding = semantic_matcher.compute_embeddings([query], role='query')[0]
    passage_embeddings = semantic_matcher.compute_embeddings(
        [paraphrase, unrelated],
        role='passage',
    )
    scores = passage_embeddings @ query_embedding

    assert float(scores[0]) >= config.SEMANTIC_MODEL_MIN_SCORE
    assert float(scores[1]) < config.SEMANTIC_MODEL_MIN_SCORE
    assert float(scores[0] - scores[1]) >= 0.08
