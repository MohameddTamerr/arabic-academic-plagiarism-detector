# -*- coding: utf-8 -*-
"""
Tests for ONNX Sequence Research Adapter:
- Verified offline CPU inference
- Integrity verification of ONNX artifact and manifest hash
- Proper paragraph-level offsets, scores, and status
- Safe fail-closed on corrupt or mismatched weights
"""
import os
import sys
import json
import hashlib
import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from plagiarism_detector.ai_detection.sequence_research import SequenceResearchAdapter, SequenceResearchError, file_sha256

@pytest.fixture(scope="module")
def onnx_model_assets():
    model_dir = ROOT / "models" / "ai_classifier" / "nawaf_int8"
    onnx_file = model_dir / "nawaf_int8.onnx"
    manifest_file = model_dir / "nawaf_int8.onnx.manifest.json"
    hashes_file = model_dir / "hashes_nawaf.json"

    if not onnx_file.is_file() or not manifest_file.is_file() or not hashes_file.is_file():
        pytest.skip("Nawaf ONNX model assets not present")

    file_hashes = json.loads(hashes_file.read_text(encoding="utf-8"))
    manifest_hash = file_sha256(manifest_file)
    return {
        "model_dir": str(model_dir),
        "onnx_artifact": str(onnx_file),
        "file_hashes": file_hashes,
        "manifest_hash": manifest_hash,
    }


def test_onnx_adapter_inference(onnx_model_assets):
    adapter = SequenceResearchAdapter(
        onnx_model_assets["model_dir"],
        file_hashes=onnx_model_assets["file_hashes"],
        label_mapping={0: "HUMAN", 1: "AI_GENERATED"},
        mapping_evidence="nawaf11570 card (0=human, 1=ai)",
        onnx_artifact=onnx_model_assets["onnx_artifact"],
        onnx_mode="int8",
        onnx_manifest_sha256=onnx_model_assets["manifest_hash"],
        batch_size=2,
    )
    paragraphs = [
        {"paragraph_id": 1, "page_number": 1, "text": "تعتبر حماية الآثار والتحف القديمة من أهم الواجبات القانونية للدولة.", "start_offset": 0, "end_offset": 66},
        {"paragraph_id": 2, "page_number": 1, "text": "", "start_offset": 67, "end_offset": 67},
        {"paragraph_id": 3, "page_number": 2, "text": "هذا بحث أكاديمي تم توليده بصيغة آلية ذكية.", "start_offset": 68, "end_offset": 109},
    ]

    results = adapter.analyze(paragraphs)
    assert len(results) == 3

    # Para 1: Eligible
    p1 = results[0]
    assert p1["paragraph_id"] == 1
    assert p1["page_number"] == 1
    assert p1["start_offset"] == 0
    assert p1["status"] == "experimental_score"
    assert "HUMAN" in p1["scores"] and "AI_GENERATED" in p1["scores"]
    assert abs(p1["scores"]["HUMAN"] + p1["scores"]["AI_GENERATED"] - 1.0) < 1e-4

    # Para 2: Empty
    p2 = results[1]
    assert p2["status"] == "not_analyzed"
    assert p2["reason"] == "empty_text"
    assert p2["scores"] is None

    # Para 3: Eligible
    p3 = results[2]
    assert p3["status"] == "experimental_score"
    assert p3["scores"]["AI_GENERATED"] >= 0.0

    # Provenance
    prov = adapter.provenance()
    assert prov["backend"] == "onnxruntime"
    assert prov["device"] == "cpu"
    assert prov["precision"] == "int8"

    adapter.close()
    assert adapter.onnx_session is None


def test_onnx_adapter_tampered_manifest_fails_closed(onnx_model_assets):
    with pytest.raises(SequenceResearchError):
        adapter = SequenceResearchAdapter(
            onnx_model_assets["model_dir"],
            file_hashes=onnx_model_assets["file_hashes"],
            label_mapping={0: "HUMAN", 1: "AI_GENERATED"},
            mapping_evidence="nawaf11570 card (0=human, 1=ai)",
            onnx_artifact=onnx_model_assets["onnx_artifact"],
            onnx_mode="int8",
            onnx_manifest_sha256="0" * 64,  # Invalid hash
        )
        adapter.load()
