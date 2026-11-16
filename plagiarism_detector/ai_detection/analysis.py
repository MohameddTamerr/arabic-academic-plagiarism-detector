"""Fail-closed integration contract and research inference pipeline for offline AI writing analysis.

No classifier is approved for unmonitored production scoring. Standard production
analysis preserves the fail-closed status. Experimental research inference is
available via analyze_document_ai_research.
"""
import json
import logging
import sys
from pathlib import Path
from threading import RLock

logger = logging.getLogger(__name__)

_RESEARCH_ADAPTER = None
_ADAPTER_LOCK = RLock()


def unavailable_analysis(enabled=False, *, failed=False):
    reason = 'no_validated_model' if enabled else 'disabled'
    if failed:
        reason = 'analysis_error'
    return {
        'status': 'unavailable',
        'reason': reason,
        'validation_status': 'no_validated_model',
        'estimated_ai_percentage': None,
        'estimated_human_percentage': None,
        'uncertain_percentage': None,
        'unanalyzed_percentage': None,
        'paragraphs': [],
        'model': None,
        'limitations': ('تعذر تحليل الكتابة بالذكاء الاصطناعي.' if failed else
                        'لا يتوفر نموذج مدقق؛ لا يمكن استنتاج مصدر النص أو نسبته.'),
    }


def public_ai_analysis(stored):
    """Expose the AI analysis payload for public/report endpoints.

    If research mode completed an analysis, it is returned intact.
    Otherwise, the contract returns the safe fail-closed unavailable state.
    """
    if isinstance(stored, dict) and stored.get('status') == 'completed':
        return dict(stored)
    reason = stored.get('reason') if isinstance(stored, dict) else None
    return unavailable_analysis(reason != 'disabled', failed=reason == 'analysis_error')


def get_research_adapter(model_variant='nawaf_int8'):
    """Lazy-load the offline research sequence classifier adapter with thread safety.

    Supports:
    1. ONNX Runtime INT8 (preferred for standalone Windows executable, lightweight, CPU-optimized, does NOT require PyTorch)
    2. TorchScript INT8 JIT (when PyTorch runtime is available)
    3. Transformers Eager (when full PyTorch is available)
    """
    global _RESEARCH_ADAPTER
    with _ADAPTER_LOCK:
        if _RESEARCH_ADAPTER is not None:
            return _RESEARCH_ADAPTER

        from .sequence_research import SequenceResearchAdapter, file_sha256

        root = Path(__file__).resolve().parent.parent.parent
        bundle_root = Path(getattr(sys, '_MEIPASS', root)).resolve()

        candidates = [
            bundle_root / 'models' / 'ai_classifier' / 'nawaf_int8',
            root / 'models' / 'ai_classifier' / 'nawaf_int8',
            root / 'scratch' / 'stage8f' / 'nawaf',
        ]
        nawaf_dir = None
        for cand in candidates:
            if cand.is_dir() and (cand / 'config.json').is_file():
                nawaf_dir = cand
                break

        if nawaf_dir is None:
            logger.warning('Nawaf model directory not found; research adapter unavailable.')
            return None

        hashes_file = nawaf_dir / 'hashes_nawaf.json'
        if not hashes_file.is_file():
            hashes_file = root / 'scratch' / 'stage8f' / 'hashes_nawaf.json'

        if not hashes_file.is_file():
            logger.warning('Nawaf model hashes file not found; research adapter unavailable.')
            return None

        file_hashes = json.loads(hashes_file.read_text(encoding='utf-8'))
        label_mapping = {0: 'HUMAN', 1: 'AI_GENERATED'}

        # 1. Prefer ONNX INT8 model (standalone, CPU-optimized, does NOT require PyTorch)
        onnx_file = nawaf_dir / 'nawaf_int8.onnx'
        if not onnx_file.is_file():
            onnx_file = root / 'scratch' / 'onnx_trial' / 'nawaf_int8.onnx'
        onnx_manifest = nawaf_dir / 'nawaf_int8.onnx.manifest.json'
        if not onnx_manifest.is_file():
            onnx_manifest = root / 'models' / 'ai_classifier' / 'nawaf_int8' / 'nawaf_int8.onnx.manifest.json'

        try:
            import onnxruntime  # noqa: F401
            has_onnx = True
        except ImportError:
            has_onnx = False

        if has_onnx and onnx_file.is_file() and onnx_manifest.is_file():
            manifest_hash = file_sha256(onnx_manifest)
            _RESEARCH_ADAPTER = SequenceResearchAdapter(
                str(nawaf_dir),
                file_hashes=file_hashes,
                label_mapping=label_mapping,
                mapping_evidence='nawaf11570 card (0=human, 1=ai)',
                onnx_artifact=str(onnx_file),
                onnx_mode='int8',
                onnx_manifest_sha256=manifest_hash,
                batch_size=4,
            )
            return _RESEARCH_ADAPTER

        # 2. Fallback to TorchScript INT8 JIT if PyTorch runtime is available
        jit_file = nawaf_dir / 'nawaf_int8.jit'
        if not jit_file.is_file():
            jit_file = root / 'scratch' / 'stage8h' / 'nawaf_int8.jit'

        manifest_file = nawaf_dir / 'nawaf_int8.manifest.json'
        if not manifest_file.is_file():
            manifest_file = root / 'scratch' / 'stage8h' / 'nawaf_int8.manifest.json'

        try:
            import torch  # noqa: F401
            has_torch = True
        except ImportError:
            has_torch = False

        if has_torch and jit_file.is_file() and manifest_file.is_file():
            manifest_hash = file_sha256(manifest_file)
            _RESEARCH_ADAPTER = SequenceResearchAdapter(
                str(nawaf_dir),
                file_hashes=file_hashes,
                label_mapping=label_mapping,
                mapping_evidence='nawaf11570 card (0=human, 1=ai)',
                scripted_artifact=str(jit_file),
                scripted_mode='int8',
                scripted_manifest_sha256=manifest_hash,
                batch_size=4,
            )
            return _RESEARCH_ADAPTER

        if has_torch and (nawaf_dir / 'model.safetensors').is_file():
            _RESEARCH_ADAPTER = SequenceResearchAdapter(
                str(nawaf_dir),
                file_hashes=file_hashes,
                label_mapping=label_mapping,
                mapping_evidence='nawaf11570 card (0=human, 1=ai)',
                batch_size=4,
            )
            return _RESEARCH_ADAPTER

        logger.warning('Neither ONNX Runtime nor PyTorch model available; research adapter disabled.')
        return None


def analyze_document_ai_research(raw_text, pages_data=None, model_variant='nawaf_int8',
                                 abstain_low=0.35, abstain_high=0.65):
    """Execute paragraph-level offline AI detection in experimental research mode.

    Preserves exact paragraph offsets, page numbers, and word counts.
    Returns word-weighted aggregate scores with calibrated confidence and abstention.
    """
    try:
        from .paragraphs import iter_paragraphs

        adapter = get_research_adapter(model_variant=model_variant)
        if adapter is None:
            return unavailable_analysis(enabled=True)

        raw_paragraphs = list(iter_paragraphs(raw_text, pages=pages_data))
        if not raw_paragraphs:
            return unavailable_analysis(enabled=True)

        results = adapter.analyze(raw_paragraphs)
        total_words = 0
        ai_words = 0
        human_words = 0
        uncertain_words = 0
        unanalyzed_words = 0

        enriched = []
        for p, res in zip(raw_paragraphs, results):
            wc = res.get('word_count', len(p.get('text', '').split()))
            total_words += wc
            scores = res.get('scores')

            if scores is None:
                unanalyzed_words += wc
                classification = 'UNANALYZED'
                confidence = 'NONE'
                ai_prob = None
                human_prob = None
            else:
                ai_prob = scores.get('AI_GENERATED', 0.0)
                human_prob = scores.get('HUMAN', 0.0)

                if ai_prob >= abstain_high:
                    classification = 'AI_GENERATED'
                    confidence = 'HIGH' if ai_prob >= 0.85 else 'MODERATE'
                    ai_words += wc
                elif ai_prob <= abstain_low:
                    classification = 'HUMAN'
                    confidence = 'HIGH' if ai_prob <= 0.15 else 'MODERATE'
                    human_words += wc
                else:
                    classification = 'UNCERTAIN'
                    confidence = 'LOW'
                    uncertain_words += wc

            entry = {
                'paragraph_id': p.get('paragraph_id'),
                'page_number': p.get('page_number'),
                'page_index': p.get('page_index'),
                'source_file': p.get('source_file'),
                'start_offset': p.get('start_offset'),
                'end_offset': p.get('end_offset'),
                'document_start_offset': p.get('document_start_offset'),
                'document_end_offset': p.get('document_end_offset'),
                'text': p.get('text'),
                'word_count': wc,
                'status': res.get('status'),
                'truncated': res.get('truncated', False),
                'ai_probability': round(ai_prob, 4) if ai_prob is not None else None,
                'human_probability': round(human_prob, 4) if human_prob is not None else None,
                'classification': classification,
                'confidence': confidence,
            }
            enriched.append(entry)

        denom = max(1, total_words)
        ai_pct = (ai_words / denom) * 100.0
        human_pct = (human_words / denom) * 100.0
        uncertain_pct = (uncertain_words / denom) * 100.0
        unanalyzed_pct = (unanalyzed_words / denom) * 100.0

        return {
            'status': 'completed',
            'mode': 'research_experimental',
            'validation_status': 'preliminary_academic_validation',
            'model': 'Nawaf-AraBERT-INT8-Offline' if model_variant == 'nawaf_int8' else 'Nawaf-AraBERT-FP32-Offline',
            'total_words_analyzed': total_words,
            'paragraphs_count': len(enriched),
            'estimated_ai_percentage': round(ai_pct, 2),
            'estimated_human_percentage': round(human_pct, 2),
            'uncertain_percentage': round(uncertain_pct, 2),
            'unanalyzed_percentage': round(unanalyzed_pct, 2),
            'paragraphs': enriched,
            'limitations': ('نتائج الفحص استكشافية بحثية لاختبار الكتابة بالذكاء الاصطناعي (AraBERT)، '
                            'ولا تعد إدانة قاطعة بالتوليد الآلي حيث قد تتأثر بعمليات التدقيق اللغوي وإعادة الصياغة.'),
        }
    except Exception as exc:
        logger.error(f'Error executing research AI analysis: {exc}', exc_info=True)
        return unavailable_analysis(enabled=True, failed=True)

