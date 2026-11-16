"""Tiny random checkpoint tests; these models are not authorship detectors."""
import hashlib
import json
import socket
import sys

import pytest

from plagiarism_detector.ai_detection.pretrained_research import HamedResearchAdapter, ResearchAdapterError, dediacritize


@pytest.fixture(scope='module')
def tiny_artifacts(tmp_path_factory):
    torch = pytest.importorskip('torch')
    transformers = pytest.importorskip('transformers')
    from torch import nn
    root = tmp_path_factory.mktemp('tiny_research_model')
    vocab = ['[PAD]', '[UNK]', '[CLS]', '[SEP]', '[MASK]', 'هذا', 'نص', 'عربي', 'اختبار']
    vocab_file = root / 'vocab.txt'
    vocab_file.write_text('\n'.join(vocab), encoding='utf-8')
    config = transformers.BertConfig(vocab_size=len(vocab), hidden_size=8, num_hidden_layers=1,
        num_attention_heads=2, intermediate_size=16, max_position_embeddings=64)
    config.save_pretrained(root)
    tokenizer = transformers.BertTokenizer(str(vocab_file), do_lower_case=False)
    tokenizer.save_pretrained(root)
    class Head(nn.Module):
        def __init__(self):
            super().__init__()
            self.dense = nn.Linear(8, 8)
            self.dropout = nn.Dropout(0.1)
            self.out_proj = nn.Linear(8, 1)
    class Model(nn.Module):
        def __init__(self):
            super().__init__()
            self.transformer = transformers.AutoModel.from_config(config)
            self.custom_head = Head()
    path = root / 'tiny-random-state.pt'
    torch.save(Model().state_dict(), path)
    return root, path, hashlib.sha256(path.read_bytes()).hexdigest()


def adapter(root, path, digest, **overrides):
    params = dict(checkpoint_sha256=digest, label_mapping={0: 'AI_GENERATED', 1: 'HUMAN'},
        label_mapping_evidence='repository plot labels; fixture only', preprocessing='original', batch_size=2, max_length=16)
    params.update(overrides)
    return HamedResearchAdapter(root, path, **params)


def test_repository_dediacritization_is_precise():
    assert dediacritize('عَلَمٌ مُهِمّ') == 'علم مهم'
    assert dediacritize('ا\u065f\u0670') == 'ا\u065f\u0670'


def test_offline_local_model_load_batch_and_page_preservation(tiny_artifacts, monkeypatch):
    root, path, digest = tiny_artifacts
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('network attempted'))
    model = adapter(root, path, digest)
    assert model.model is None
    paragraphs = [{'paragraph_id': i, 'page_number': i + 1, 'text': 'هذا نص عربي'} for i in range(3)]
    results = model.analyze(paragraphs)
    assert len(results) == 3
    assert [r['page_number'] for r in results] == [1, 2, 3]
    assert all(r['class_1_label'] == 'HUMAN' and r['research_only'] and not r['calibrated'] for r in results)
    assert all(0 <= r['class_1_score'] <= 1 for r in results)
    assert all(r['text'] == 'هذا نص عربي' and not r['truncated'] for r in results)
    assert model.analyze([{'text': ' '.join(['نص'] * 30)}])[0]['truncated'] is True
    filtered = adapter(root, path, digest, preprocessing='repository_dediacritized')
    item = filtered.analyze([{'text': 'هَذا نَصّ عَربي', 'page_number': 4}])[0]
    assert item['text'] == 'هَذا نَصّ عَربي' and item['page_number'] == 4
    assert item['preprocessing'] == 'repository_dediacritized'


def test_missing_bad_hash_and_mapping_fail_closed(tiny_artifacts, tmp_path):
    root, path, digest = tiny_artifacts
    with pytest.raises(ResearchAdapterError, match='missing'):
        adapter(root, tmp_path / 'absent.pt', digest)
    with pytest.raises(ResearchAdapterError, match='SHA-256'):
        adapter(root, path, '0' * 64)
    with pytest.raises(ResearchAdapterError, match='mapping'):
        adapter(root, path, digest, label_mapping={0: 'HUMAN', 1: 'UNKNOWN'})
    with pytest.raises(ResearchAdapterError, match='evidence'):
        adapter(root, path, digest, label_mapping_evidence='')


def test_corrupt_and_incompatible_checkpoints_fail_closed(tiny_artifacts, tmp_path):
    import torch
    root, _, _ = tiny_artifacts
    corrupt = tmp_path / 'corrupt.pt'
    corrupt.write_bytes(b'not a model')
    m = adapter(root, corrupt, hashlib.sha256(corrupt.read_bytes()).hexdigest())
    with pytest.raises(ResearchAdapterError, match='failed validation'):
        m.load()
    wrong = tmp_path / 'wrong.pt'
    torch.save({'custom_head.out_proj.weight': torch.zeros((1, 1))}, wrong)
    m = adapter(root, wrong, hashlib.sha256(wrong.read_bytes()).hexdigest())
    with pytest.raises(ResearchAdapterError, match='failed validation'):
        m.load()


def test_missing_tokenizer_and_inference_error_fail_safely(tiny_artifacts, tmp_path, monkeypatch):
    root, path, digest = tiny_artifacts
    bare = tmp_path / 'bare'
    bare.mkdir()
    (bare / 'config.json').write_bytes((root / 'config.json').read_bytes())
    with pytest.raises(ResearchAdapterError, match='failed validation'):
        adapter(bare, path, digest).load()
    m = adapter(root, path, digest)
    m.load()
    monkeypatch.setattr(m.model, 'forward', lambda **kw: (_ for _ in ()).throw(RuntimeError('private text')))
    with pytest.raises(ResearchAdapterError, match='no scores returned') as error:
        m.analyze([{'text': 'نص خاص'}])
    assert 'private text' not in str(error.value)


def test_research_evaluation_cli_uses_local_fixture_without_disclosing_text(tiny_artifacts, tmp_path, monkeypatch, capsys):
    from tools.evaluate_pretrained_research import main
    root, path, digest = tiny_artifacts
    data = tmp_path / 'data.json'
    data.write_text(json.dumps([{'sample_id': 'a', 'text': 'هذا نص عربي', 'provenance_label': 'HUMAN'},
                                {'sample_id': 'b', 'text': 'نص عربي اختبار', 'provenance_label': 'AI_GENERATED'}], ensure_ascii=False), encoding='utf-8')
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps({'dataset_use_authorized': True, 'model_use_authorized': True,
        'independent_evaluation_attested': True, 'dataset_authorization_reference': 'fixture',
        'model_authorization_reference': 'fixture'}), encoding='utf-8')
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('network attempted'))
    monkeypatch.setattr(sys, 'argv', ['tool', '--model-dir', str(root), '--checkpoint', str(path),
        '--checkpoint-sha256', digest, '--data', str(data), '--manifest', str(manifest), '--class-one', 'HUMAN',
        '--label-mapping-evidence', 'fixture', '--preprocessing', 'original', '--ai-threshold', '0.8'])
    main()
    output = capsys.readouterr().out
    report = json.loads(output)
    assert report['count'] == 2 and report['research_only']
    assert sum(map(sum, report['confusion_matrix'])) == 2
    assert 'هذا نص عربي' not in output
