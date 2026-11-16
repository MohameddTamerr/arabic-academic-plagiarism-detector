"""Research-only adapter for the Hamed et al. single-logit checkpoint layout.

Not imported by the Flask app. Scores are uncalibrated and are not a finding
of authorship. Only load trusted, rights-cleared local model files.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from threading import RLock

from .paragraphs import MAX_PARAGRAPH_CHARACTERS, paragraph_evidence


class ResearchAdapterError(Exception):
    """A safe, document-free error from the research adapter."""


def dediacritize(text):
    """Match the repository's Diacritics-Free branch: U+064B..U+065E."""
    return ''.join(c for c in text if not 0x064B <= ord(c) < 0x065F)


def _sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


class HamedResearchAdapter:
    def __init__(self, model_dir, checkpoint, *, checkpoint_sha256, label_mapping,
                 label_mapping_evidence, preprocessing, batch_size=4, max_length=512):
        self.model_dir = Path(model_dir)
        self.checkpoint = Path(checkpoint)
        if not self.model_dir.is_dir() or not self.checkpoint.is_file():
            raise ResearchAdapterError('Local model directory or checkpoint is missing.')
        if (not isinstance(checkpoint_sha256, str) or len(checkpoint_sha256) != 64 or
            any(c not in '0123456789abcdefABCDEF' for c in checkpoint_sha256)):
            raise ResearchAdapterError('A trusted SHA-256 is required.')
        try:
            actual_hash = _sha256(self.checkpoint)
        except OSError as exc:
            raise ResearchAdapterError('Unable to read local checkpoint.') from exc
        if actual_hash != checkpoint_sha256.lower():
            raise ResearchAdapterError('Checkpoint SHA-256 does not match.')
        self.checkpoint_sha256 = checkpoint_sha256.lower()
        if label_mapping not in ({0: 'AI_GENERATED', 1: 'HUMAN'}, {0: 'HUMAN', 1: 'AI_GENERATED'}):
            raise ResearchAdapterError('An explicit binary label mapping is required.')
        if not isinstance(label_mapping_evidence, str) or not label_mapping_evidence.strip():
            raise ResearchAdapterError('Documented label-mapping evidence is required.')
        if preprocessing not in ('original', 'repository_dediacritized'):
            raise ResearchAdapterError('Explicit checkpoint preprocessing is required.')
        if type(batch_size) is not int or not 1 <= batch_size <= 32 or type(max_length) is not int or not 1 <= max_length <= 512:
            raise ResearchAdapterError('Invalid batch size or token limit.')
        self.label_mapping = dict(label_mapping)
        self.label_mapping_evidence = label_mapping_evidence
        self.preprocessing = preprocessing
        self.batch_size = batch_size
        self.max_length = max_length
        self._lock = RLock()
        self.model = None
        self.tokenizer = None

    def load(self):
        """Load the full state dict strictly, lazily, on CPU, with no network."""
        with self._lock:
            self._load()

    def _load(self):
        if self.model is not None:
            return
        try:
            if _sha256(self.checkpoint) != self.checkpoint_sha256:
                raise ResearchAdapterError('Checkpoint SHA-256 does not match.')
            import torch
            from torch import nn
            from transformers import AutoConfig, AutoModel, AutoTokenizer

            config = AutoConfig.from_pretrained(str(self.model_dir), local_files_only=True, trust_remote_code=False)
            if config.model_type not in {'bert', 'electra', 'xlm-roberta'}:
                raise ResearchAdapterError('Unsupported encoder architecture.')
            tokenizer_files = ('tokenizer.json', 'vocab.txt', 'sentencepiece.bpe.model', 'spiece.model')
            if not any((self.model_dir / name).is_file() for name in tokenizer_files):
                raise ResearchAdapterError('Local model, tokenizer, or checkpoint failed validation.')
            tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), local_files_only=True, trust_remote_code=False)
            if len(tokenizer) < 6 or len(tokenizer) > config.vocab_size:
                raise ResearchAdapterError('Local model, tokenizer, or checkpoint failed validation.')

            class CustomHead(nn.Module):
                def __init__(self, hidden_size):
                    super().__init__()
                    self.dense = nn.Linear(hidden_size, hidden_size)
                    self.dropout = nn.Dropout(0.1)
                    self.out_proj = nn.Linear(hidden_size, 1)

                def forward(self, values):
                    return self.out_proj(self.dropout(self.dense(values)))

            class CustomModel(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.transformer = AutoModel.from_config(config, trust_remote_code=False)
                    self.custom_head = CustomHead(config.hidden_size)

                def forward(self, input_ids, attention_mask):
                    outputs = self.transformer(input_ids=input_ids, attention_mask=attention_mask)
                    return self.custom_head(outputs.last_hidden_state[:, 0, :])

            model = CustomModel()
            state = torch.load(str(self.checkpoint), map_location='cpu', weights_only=True)
            model.load_state_dict(state, strict=True)
            model.eval()
        except ResearchAdapterError:
            raise
        except Exception as exc:
            raise ResearchAdapterError('Local model, tokenizer, or checkpoint failed validation.') from exc
        self.model, self.tokenizer = model, tokenizer

    def analyze(self, paragraphs):
        """Return raw sigmoid scores, keeping original text and page metadata."""
        with self._lock:
            return self._analyze(paragraphs)

    def _analyze(self, paragraphs):
        if not isinstance(paragraphs, list) or any(not isinstance(p, dict) or not isinstance(p.get('text'), str) for p in paragraphs):
            raise ResearchAdapterError('Paragraphs must contain text strings.')
        if any(not p['text'].strip() for p in paragraphs):
            raise ResearchAdapterError('Empty paragraphs cannot be analyzed.')
        if any(len(p['text']) > MAX_PARAGRAPH_CHARACTERS for p in paragraphs):
            raise ResearchAdapterError('Paragraph exceeds the research input length limit.')
        if not paragraphs:
            return []
        self._load()
        try:
            import torch
            results = []
            with torch.inference_mode():
                for start in range(0, len(paragraphs), self.batch_size):
                    chunk = paragraphs[start:start + self.batch_size]
                    texts = [dediacritize(p['text']) if self.preprocessing == 'repository_dediacritized' else p['text'] for p in chunk]
                    lengths = [len(tokens) for tokens in self.tokenizer(texts, truncation=False)['input_ids']]
                    inputs = self.tokenizer(texts, padding=True, truncation=True, max_length=self.max_length, return_tensors='pt')
                    logits = self.model(input_ids=inputs['input_ids'].cpu(), attention_mask=inputs['attention_mask'].cpu())
                    scores = torch.sigmoid(logits).reshape(-1).tolist()
                    if len(scores) != len(chunk):
                        raise ValueError('unexpected model output shape')
                    for paragraph, score, length in zip(chunk, scores, lengths):
                        if not 0 <= score <= 1:
                            raise ValueError('invalid model score')
                        results.append({**paragraph_evidence(paragraph),
                            'class_1_score': float(score), 'class_1_label': self.label_mapping[1],
                            'class_0_label': self.label_mapping[0], 'truncated': length > self.max_length,
                            'preprocessing': self.preprocessing, 'calibrated': False, 'research_only': True,
                            'model_sha256': self.checkpoint_sha256, 'classification': None,
                            'model_validation_status': 'not_validated', 'decision_status': 'INSUFFICIENT_EVIDENCE'})
            return results
        except Exception as exc:
            raise ResearchAdapterError('Research inference failed; no scores returned.') from exc
