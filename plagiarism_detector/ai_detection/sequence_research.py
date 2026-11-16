"""Local-only, CPU-only sequence-classifier research inference; not production."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock

from .paragraphs import MAX_PARAGRAPH_CHARACTERS, paragraph_evidence


class SequenceResearchError(Exception):
    pass


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_package(artifact, source_hash, mode, *, manifest_sha256=None):
    raw = artifact.with_suffix('.manifest.json').read_bytes()
    if manifest_sha256 is not None and hashlib.sha256(raw).hexdigest() != manifest_sha256.lower():
        raise ValueError('artifact manifest hash mismatch')
    meta = json.loads(raw)
    if meta['mode'] != mode or meta['source_sha256'] != source_hash or file_sha256(artifact) != meta['sha256']:
        raise ValueError('artifact identity mismatch')
    return meta


class SequenceResearchAdapter:
    """Require explicit trusted hashes and source-evidenced class mapping."""
    def __init__(self, model_dir, *, file_hashes, label_mapping, mapping_evidence,
                 batch_size=4, max_length=512, scripted_artifact=None,
                 scripted_mode=None, scripted_manifest_sha256=None,
                 onnx_artifact=None, onnx_mode=None, onnx_manifest_sha256=None):
        self.model_dir = Path(model_dir).resolve()
        if not self.model_dir.is_dir():
            raise SequenceResearchError('Local model directory missing.')
        if not isinstance(file_hashes, dict) or not {'config.json', 'model.safetensors'} <= file_hashes.keys():
            raise SequenceResearchError('Hash manifest must cover model and configuration.')
        if not {'tokenizer.json', 'vocab.txt'}.intersection(file_hashes):
            raise SequenceResearchError('Hash manifest must cover tokenizer vocabulary.')
        # Every tokenizer-related asset present must be pinned too.
        for name in ('tokenizer.json', 'vocab.txt', 'tokenizer_config.json', 'special_tokens_map.json',
                     'added_tokens.json'):
            if (self.model_dir / name).exists() and name not in file_hashes:
                raise SequenceResearchError('Hash manifest does not cover tokenizer files.')
        if label_mapping not in ({0: 'HUMAN', 1: 'AI_GENERATED'}, {0: 'AI_GENERATED', 1: 'HUMAN'}):
            raise SequenceResearchError('Explicit binary label mapping required.')
        if not isinstance(mapping_evidence, str) or not mapping_evidence.strip():
            raise SequenceResearchError('Label mapping evidence required.')
        if type(batch_size) is not int or not 1 <= batch_size <= 32 or type(max_length) is not int or not 1 <= max_length <= 512:
            raise SequenceResearchError('Invalid batch size or token limit.')
        self.file_hashes = dict(file_hashes)
        self.label_mapping = dict(label_mapping)
        self.mapping_evidence = mapping_evidence
        self.batch_size, self.max_length = batch_size, max_length
        self.scripted_artifact = Path(scripted_artifact).resolve() if scripted_artifact is not None else None
        self.scripted_mode = scripted_mode
        self.scripted_manifest_sha256 = scripted_manifest_sha256
        if self.scripted_artifact is not None and (
            scripted_mode not in ('fp32', 'int8') or not isinstance(scripted_manifest_sha256, str)
            or len(scripted_manifest_sha256) != 64
            or any(char not in '0123456789abcdefABCDEF' for char in scripted_manifest_sha256)
        ):
            raise SequenceResearchError('A trusted TorchScript manifest hash and mode are required.')

        self.onnx_artifact = Path(onnx_artifact).resolve() if onnx_artifact is not None else None
        self.onnx_mode = onnx_mode
        self.onnx_manifest_sha256 = onnx_manifest_sha256
        if self.onnx_artifact is not None and (
            onnx_mode not in ('fp32', 'int8', 'onnx_int8') or not isinstance(onnx_manifest_sha256, str)
            or len(onnx_manifest_sha256) != 64
            or any(char not in '0123456789abcdefABCDEF' for char in onnx_manifest_sha256)
        ):
            raise SequenceResearchError('A trusted ONNX manifest hash and mode are required.')

        self._lock = RLock()
        self._scripted_sha256 = None
        self._onnx_sha256 = None
        self.model = self.tokenizer = self.onnx_session = None
        self._tokenizer_kind = None
        self._verify_files()

    def _verify_files(self):
        try:
            for name, expected in self.file_hashes.items():
                if not isinstance(name, str) or Path(name).name != name:
                    raise SequenceResearchError('Invalid model asset name.')
                if not isinstance(expected, str) or len(expected) != 64 or any(
                    char not in '0123456789abcdefABCDEF' for char in expected
                ):
                    raise SequenceResearchError('Invalid model asset hash.')
                if (self.scripted_artifact is not None or self.onnx_artifact is not None) and name == 'model.safetensors':
                    continue  # The pinned artifact manifest binds the source digest.
                path = (self.model_dir / name).resolve()
                if path.parent != self.model_dir or not path.is_file():
                    raise SequenceResearchError('Missing or invalid model asset.')
                if file_sha256(path) != expected.lower():
                    raise SequenceResearchError('Model asset hash mismatch.')
        except OSError as exc:
            raise SequenceResearchError('Unable to read local model assets.') from exc

    def close(self):
        """Release this adapter's references; allocator/OS RSS may not fall immediately."""
        with self._lock:
            self.model = self.tokenizer = self.onnx_session = None
            self._scripted_sha256 = None
            self._onnx_sha256 = None

    def provenance(self):
        with self._lock:
            backend = 'onnxruntime' if self.onnx_artifact else ('torchscript' if self.scripted_artifact else 'transformers')
            precision = self.onnx_mode if self.onnx_artifact else (self.scripted_mode if self.scripted_artifact else 'fp32')
            return {
                'backend': backend,
                'device': 'cpu',
                'precision': precision,
                'file_hashes_sha256': {name: digest.lower() for name, digest in self.file_hashes.items()},
                'artifact_sha256': self._onnx_sha256 if self.onnx_artifact else self._scripted_sha256,
                'artifact_manifest_sha256': self.onnx_manifest_sha256 if self.onnx_artifact else self.scripted_manifest_sha256,
                'label_mapping': dict(self.label_mapping),
                'label_mapping_evidence': self.mapping_evidence,
                'max_length': self.max_length,
                'batch_size': self.batch_size,
                'validation_status': 'not_validated',
            }

    def load(self):
        with self._lock:
            self._load()

    def _load(self):
        if self.model is not None or self.onnx_session is not None:
            return
        self._verify_files()
        try:
            if self.onnx_artifact is not None:
                import onnxruntime as ort
                raw_man = self.onnx_artifact.with_suffix('.onnx.manifest.json')
                if not raw_man.is_file():
                    raw_man = self.onnx_artifact.with_suffix('.manifest.json')
                raw_bytes = raw_man.read_bytes()
                if self.onnx_manifest_sha256 is not None:
                    if hashlib.sha256(raw_bytes).hexdigest() != self.onnx_manifest_sha256.lower():
                        raise ValueError('ONNX manifest hash mismatch')
                meta = json.loads(raw_bytes)
                if file_sha256(self.onnx_artifact) != meta['sha256']:
                    raise ValueError('ONNX artifact identity mismatch')

                sess_opts = ort.SessionOptions()
                sess_opts.intra_op_num_threads = 2
                sess_opts.inter_op_num_threads = 1
                sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                self.onnx_session = ort.InferenceSession(str(self.onnx_artifact), sess_opts, providers=['CPUExecutionProvider'])
                self._onnx_sha256 = meta['sha256']

                # Initialize Tokenizer: prefer tokenizers, fallback to transformers
                try:
                    import tokenizers
                    tok = tokenizers.Tokenizer.from_file(str(self.model_dir / 'tokenizer.json'))
                    tok.enable_padding(length=self.max_length, pad_id=0, pad_token='[PAD]')
                    tok.enable_truncation(max_length=self.max_length)
                    self.tokenizer = tok
                    self._tokenizer_kind = 'tokenizers'
                except Exception:
                    from transformers import AutoTokenizer
                    self.tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), local_files_only=True, trust_remote_code=False)
                    self._tokenizer_kind = 'transformers'
                return

            from transformers import AutoConfig, AutoTokenizer
            config = AutoConfig.from_pretrained(str(self.model_dir), local_files_only=True, trust_remote_code=False)
            if config.num_labels != 2 or config.model_type != 'bert':
                raise SequenceResearchError('Expected a binary BERT classifier.')
            known = {'human': 'HUMAN', 'human-written': 'HUMAN', 'ai': 'AI_GENERATED', 'ai-generated': 'AI_GENERATED'}
            declared = {i: known.get(str(config.id2label.get(i, '')).strip().lower()) for i in (0, 1)}
            if any(label and label != self.label_mapping[index] for index, label in declared.items()):
                raise SequenceResearchError('Provided labels conflict with model configuration.')
            tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), local_files_only=True, trust_remote_code=False)
            if len(tokenizer) < 6 or len(tokenizer) > config.vocab_size:
                raise SequenceResearchError('Tokenizer vocabulary is incompatible.')
            if self.scripted_artifact is not None:
                import torch
                meta = verify_package(
                    self.scripted_artifact, self.file_hashes['model.safetensors'].lower(), self.scripted_mode,
                    manifest_sha256=self.scripted_manifest_sha256,
                )
                if self.scripted_mode == 'int8':
                    torch.backends.quantized.engine = 'onednn'
                model = torch.jit.load(str(self.scripted_artifact), map_location='cpu').eval()
                self._scripted_sha256 = meta['sha256']
            else:
                from transformers import AutoModelForSequenceClassification

                model, info = AutoModelForSequenceClassification.from_pretrained(
                    str(self.model_dir), config=config, local_files_only=True, trust_remote_code=False,
                    use_safetensors=True, output_loading_info=True, ignore_mismatched_sizes=False)
                if info.get('missing_keys') or info.get('mismatched_keys') or info.get('error_msgs'):
                    raise SequenceResearchError('Checkpoint is missing compatible classifier weights.')
                model.to('cpu').eval()
        except SequenceResearchError:
            raise
        except Exception as exc:
            raise SequenceResearchError('Local model or tokenizer failed to load.') from exc
        self.model, self.tokenizer = model, tokenizer

    def analyze(self, paragraphs):
        with self._lock:
            return self._analyze(paragraphs)

    def _analyze(self, paragraphs):
        if not isinstance(paragraphs, list) or any(not isinstance(p, dict) or not isinstance(p.get('text'), str) for p in paragraphs):
            raise SequenceResearchError('Paragraphs must contain text strings.')
        if not paragraphs:
            return []
        try:
            output = []
            for start in range(0, len(paragraphs), self.batch_size):
                batch = paragraphs[start:start + self.batch_size]
                eligible = [p for p in batch if len(p['text']) <= MAX_PARAGRAPH_CHARACTERS and p['text'].strip()]
                scores = []
                if eligible:
                    self._load()
                    texts = [p['text'] for p in eligible]
                    if self.onnx_session is not None:
                        import numpy as np
                        if getattr(self, '_tokenizer_kind', '') == 'tokenizers':
                            encodings = self.tokenizer.encode_batch(texts)
                            input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
                            attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
                            token_type_ids = np.array([e.type_ids for e in encodings], dtype=np.int64)
                            lengths = [int(np.sum(e.attention_mask)) for e in encodings]
                        else:
                            lengths = self.tokenizer(texts, truncation=False, verbose=False, return_length=True)['length']
                            encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=self.max_length, return_tensors='np')
                            input_ids = encoded['input_ids'].astype(np.int64)
                            attention_mask = encoded['attention_mask'].astype(np.int64)
                            token_type_ids = encoded.get('token_type_ids', np.zeros_like(input_ids)).astype(np.int64)
                        ort_inputs = {
                            'input_ids': input_ids,
                            'attention_mask': attention_mask,
                            'token_type_ids': token_type_ids,
                        }
                        logits = self.onnx_session.run(None, ort_inputs)[0]
                        exp_logits = np.exp(logits - np.max(logits, axis=-1, keepdims=True))
                        probabilities = (exp_logits / np.sum(exp_logits, axis=-1, keepdims=True)).tolist()
                    else:
                        import torch
                        lengths = self.tokenizer(texts, truncation=False, verbose=False, return_length=True)['length']
                        with torch.device('cpu'), torch.inference_mode():
                            encoded = self.tokenizer(texts, padding=True, truncation=True,
                                                     max_length=self.max_length, return_tensors='pt')
                            if self.scripted_artifact:
                                logits = self.model(*(encoded[name] for name in ('input_ids', 'attention_mask', 'token_type_ids')))
                            else:
                                logits = self.model(**encoded).logits
                            probabilities = torch.softmax(logits, dim=-1).tolist()
                    if len(probabilities) != len(eligible) or any(len(p) != 2 for p in probabilities):
                        raise ValueError('invalid output dimensions')
                    for p, length in zip(probabilities, lengths):
                        if any(not 0 <= score <= 1 for score in p):
                            raise ValueError('invalid score')
                        scores.append((p, length))
                iterator = iter(scores)
                for p in batch:
                    item = paragraph_evidence(p)
                    model_hash = self._onnx_sha256 or self._scripted_sha256 or self.file_hashes.get('model.safetensors', '').lower()
                    item.update({'word_count': len(p['text'].split()), 'research_only': True, 'calibrated': False,
                        'model_sha256': model_hash,
                        'classification': None, 'model_validation_status': 'not_validated',
                        'decision_status': 'INSUFFICIENT_EVIDENCE'})
                    if len(p['text']) > MAX_PARAGRAPH_CHARACTERS:
                        item.update(status='not_analyzed', reason='input_too_long', scores=None, truncated=False)
                    elif p['text'].strip():
                        probs, length = next(iterator)
                        item.update(status='experimental_score', scores={self.label_mapping[i]: float(probs[i]) for i in range(2)},
                                    truncated=length > self.max_length)
                    else:
                        item.update(status='not_analyzed', reason='empty_text', scores=None, truncated=False)
                    output.append(item)
            return output
        except SequenceResearchError:
            raise
        except Exception as exc:
            raise SequenceResearchError('Research inference failed; no scores returned.') from exc
