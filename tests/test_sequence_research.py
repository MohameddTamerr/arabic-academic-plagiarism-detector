"""Small synthetic checkpoints test code paths, not detection accuracy."""
import hashlib
import json
import socket
import pytest

from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter, SequenceResearchError
from plagiarism_detector.ai_detection.paragraphs import MAX_PARAGRAPH_CHARACTERS, iter_paragraphs


@pytest.fixture(scope='module')
def artifacts(tmp_path_factory):
    torch = pytest.importorskip('torch')
    previous_threads = torch.get_num_threads()
    torch.set_num_threads(1)
    t = pytest.importorskip('transformers')
    root = tmp_path_factory.mktemp('sequence_tiny')
    words = ['[PAD]', '[UNK]', '[CLS]', '[SEP]', '[MASK]', 'هذا', 'نص', 'عربي', 'اختبار']
    vocab = root / 'vocab.txt'
    vocab.write_text('\n'.join(words), encoding='utf-8')
    tokenizer = t.BertTokenizer(str(vocab), do_lower_case=False)
    tokenizer.save_pretrained(root)
    config = t.BertConfig(vocab_size=len(words), hidden_size=8, num_hidden_layers=1,
        num_attention_heads=2, intermediate_size=16, max_position_embeddings=64,
        id2label={0:'Human-written', 1:'AI-generated'})
    t.AutoModelForSequenceClassification.from_config(config).save_pretrained(root, safe_serialization=True)
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()}
    yield root, files
    torch.set_num_threads(previous_threads)


def create(root, hashes, **kwargs):
    options = {'label_mapping': {0:'HUMAN', 1:'AI_GENERATED'}, 'mapping_evidence':'fixture', 'batch_size':2, 'max_length':16}
    options.update(kwargs)
    return SequenceResearchAdapter(root, file_hashes=hashes, **options)


def test_local_cpu_batched_no_network_and_metadata(artifacts, monkeypatch):
    root, hashes = artifacts
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **kw: pytest.fail('network attempted'))
    model = create(root, hashes)
    assert model.model is None
    rows = [{'paragraph_id':1, 'page_number':3, 'text':'هذا نص عربي', 'start_offset':4, 'end_offset':15},
            {'paragraph_id':2, 'text':''}, {'paragraph_id':3, 'text':' '.join(['نص']*30)}]
    result = model.analyze(rows)
    assert result[0]['text'] == rows[0]['text'] and result[0]['page_number'] == 3
    assert result[0]['start_offset'] == 4 and result[0]['classification'] is None
    assert result[0]['model_validation_status'] == 'not_validated'
    assert result[0]['decision_status'] == 'INSUFFICIENT_EVIDENCE'
    assert abs(sum(result[0]['scores'].values())-1) < 1e-5
    assert result[1]['status'] == 'not_analyzed' and result[1]['scores'] is None
    assert result[2]['truncated'] is True
    assert next(model.model.parameters()).device.type == 'cpu'


def test_hash_label_and_missing_fail_closed(artifacts, tmp_path):
    root, hashes = artifacts
    with pytest.raises(SequenceResearchError, match='missing'):
        create(tmp_path / 'missing', hashes)
    bad = dict(hashes); bad['config.json'] = '0'*64
    with pytest.raises(SequenceResearchError, match='hash'):
        create(root, bad)
    with pytest.raises(SequenceResearchError, match='mapping'):
        create(root, hashes, label_mapping={0:'X',1:'Y'})
    with pytest.raises(SequenceResearchError, match='conflict'):
        create(root, hashes, label_mapping={0:'AI_GENERATED',1:'HUMAN'}).load()


def test_missing_or_corrupt_weights_fail_closed(artifacts, tmp_path):
    root, hashes = artifacts
    missing = dict(hashes); missing.pop('model.safetensors')
    with pytest.raises(SequenceResearchError, match='manifest'):
        create(root, missing)
    for file in root.iterdir():
        if file.is_file():
            (tmp_path / file.name).write_bytes(file.read_bytes())
    (tmp_path/'model.safetensors').write_bytes(b'corrupt')
    broken = dict(hashes); broken['model.safetensors'] = hashlib.sha256(b'corrupt').hexdigest()
    with pytest.raises(SequenceResearchError, match='failed to load'):
        create(tmp_path, broken).load()


def test_lifecycle_releases_model_and_can_reload(artifacts):
    import gc
    import weakref
    root, hashes = artifacts
    model = create(root, hashes)
    model.load()
    reference = weakref.ref(model.model)
    model.close()
    gc.collect()
    assert model.model is None and model.tokenizer is None and reference() is None
    model.close()
    assert model.analyze([{'text':'هذا نص عربي'}])[0]['classification'] is None
    model.close()


def test_extracted_paragraphs_preserve_unicode_page_and_document_offsets():
    pages = [
        {'text': '  أَصلٌ\r\nالسطر التالي 🔍\r\n \r\nنهاية.', 'file_index': 0, 'page_number': 1},
        {'text': '', 'file_index': 0, 'page_number': 2},
        {'text': 'أَصلٌ\r\rالجملة الأخيرة  ', 'file_index': 1, 'page_number': 1, 'is_ocr': True},
    ]
    rows = list(iter_paragraphs('', pages))
    assert [row['text'] for row in rows] == ['  أَصلٌ\r\nالسطر التالي 🔍', 'نهاية.', 'أَصلٌ', 'الجملة الأخيرة  ']
    assert [row['page_index'] for row in rows] == [0, 0, 2, 2]
    document = '\n\n'.join(page['text'] for page in pages if page['text'])
    for row in rows:
        page = pages[row['page_index']]
        assert row['file_index'] == page['file_index']
        assert page['text'][row['start_offset']:row['end_offset']] == row['text']
        assert document[row['document_start_offset']:row['document_end_offset']] == row['text']


def test_empty_and_oversized_paragraphs_do_not_load_model(artifacts):
    model = create(*artifacts)
    rows = model.analyze([{'text': ' '}, {'text': 'ن' * (MAX_PARAGRAPH_CHARACTERS + 1)}])
    assert model.model is None
    assert [row['reason'] for row in rows] == ['empty_text', 'input_too_long']
    assert all(row['scores'] is None and row['classification'] is None for row in rows)


def test_torchscript_manifest_is_pinned_before_lazy_cpu_load(artifacts, tmp_path, monkeypatch):
    import torch

    class FixtureClassifier(torch.nn.Module):
        def forward(self, ids, attention, types):
            count = attention.sum(dim=1).float()
            return torch.stack((count, count), dim=1)

    example = torch.ones((1, 4), dtype=torch.long)
    artifact = tmp_path / 'fixture.jit'
    torch.jit.trace(FixtureClassifier(), (example, example, example)).save(str(artifact))
    root, hashes = artifacts
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = artifact.with_suffix('.manifest.json')
    manifest.write_text(json.dumps({'mode': 'fp32', 'source_sha256': hashes['model.safetensors'],
                                    'sha256': digest}), encoding='utf-8')
    options = {'scripted_artifact': artifact, 'scripted_mode': 'fp32',
               'scripted_manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **kw: pytest.fail('network attempted'))
    model = create(root, hashes, **options)
    assert model.model is None
    evidence = list(iter_paragraphs('هذا نص عربي\n\nهذا اختبار'))
    result = model.analyze(evidence)
    assert [item['text'] for item in result] == [item['text'] for item in evidence]
    assert all(item['model_sha256'] == digest and item['classification'] is None for item in result)
    assert model.provenance()['artifact_sha256'] == digest
    assert model.provenance()['device'] == 'cpu'
    model.close()
    manifest.write_text('{}', encoding='utf-8')
    with pytest.raises(SequenceResearchError):
        model.analyze(evidence)
    assert model.model is None
