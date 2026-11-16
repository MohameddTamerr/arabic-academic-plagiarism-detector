# -*- coding: utf-8 -*-
"""
Tests for Phase 20 — Release Candidate Verification & Audit Suite.
Validates:
- Integrity of the current release source manifest and critical file SHA-256 hashes
- Immutability of production default settings and thresholds
- Version registry synchronization across core modules
- Strict air-gapped zero-network invariants
- Completeness of the institutional documentation suite
- SQLite database integrity check
"""

import sys
import json
import hashlib
import re
from pathlib import Path
import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import config
import app.versioning as versioning

_MANIFEST_FILE = _ROOT / "release_source_manifest.json"
_DOCS_DIR = _ROOT / "docs"


def test_release_manifest_integrity_and_hashes():
    """Verify the frozen release input hashes against the current source tree."""
    assert _MANIFEST_FILE.exists(), f"Missing manifest: {_MANIFEST_FILE}"
    with open(_MANIFEST_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert re.fullmatch(r"windows-final-acceptance-rc(?:[1-9][0-9]*)?", manifest["release_version"])
    assert "readiness_verdict" in manifest
    assert manifest["application_version"] == versioning.APPLICATION_VERSION
    assert manifest["engine_version"] == versioning.ENGINE_VERSION

    # Verify critical file SHA-256 hashes match disk
    hashes = manifest["critical_file_hashes_sha256"]
    assert {
        'config.py', 'templates/index.html', 'app/routes/report_routes.py',
        'app/routes/scan_routes.py', 'app/routes/batch_routes.py',
        'app/repositories/batch_repo.py', 'app/security/authorization.py',
    } <= hashes.keys()
    for rel_path, expected_hash in hashes.items():
        file_path = _ROOT / rel_path
        assert file_path.exists(), f"Critical file missing: {rel_path}"
        actual_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
        assert actual_hash == expected_hash, f"Hash mismatch for {rel_path}: expected {expected_hash}, got {actual_hash}"


def test_production_defaults_strictly_unmodified():
    """Verify production settings in config.DEFAULT_SETTINGS remain strictly unchanged."""
    assert config.DEFAULT_SETTINGS['shingle_size'] == 4
    assert config.DEFAULT_SETTINGS['jaccard_threshold'] == 0.33
    assert config.DEFAULT_SETTINGS['tfidf_threshold'] == 0.35
    assert config.DEFAULT_SETTINGS['semantic_threshold'] == 0.80
    assert config.DEFAULT_SETTINGS['max_candidate_retrieval'] == 50
    assert config.DEFAULT_SETTINGS['enable_semantic_model'] is True
    assert config.DEFAULT_SETTINGS['enable_ocr'] is True


def test_version_registry_consistency():
    """Verify version registry constants in app/versioning.py."""
    assert versioning.APPLICATION_VERSION == "2.5.0"
    assert versioning.ENGINE_VERSION == "1.3.0"
    assert versioning.DATABASE_SCHEMA_VERSION == "1.0.0"
    assert versioning.REPORT_SCHEMA_VERSION == "1.0"


def test_documentation_suite_completeness():
    """Verify all required institutional documentation files exist and have non-empty content."""
    required_docs = [
        "DEPLOYMENT.md",
        "OPERATIONS.md",
        "SECURITY.md",
        "BACKUP_RESTORE.md",
        "DETECTOR_LIMITATIONS.md",
        "PILOT_GUIDE.md",
        "RELEASE_NOTES.md",
        "DETECTION_IMPROVEMENT.md",
        "DETECTOR_EVALUATION.md",
        "OCR_SETUP.md",
        "DETECTOR_CHANGELOG.md"
    ]
    for doc in required_docs:
        doc_path = _DOCS_DIR / doc
        assert doc_path.exists(), f"Missing required document: {doc}"
        assert doc_path.stat().st_size > 300, f"Document is too small or incomplete: {doc}"


def test_air_gapped_offline_zero_network_invariants(monkeypatch):
    """Verify detector components function without attempting network access."""
    import socket

    def blocked_socket(*args, **kwargs):
        raise RuntimeError("NETWORK_ACCESS_BLOCKED_AIR_GAPPED")

    monkeypatch.setattr(socket, "socket", blocked_socket)

    from plagiarism_detector.detection.semantic_matcher import check_semantic_model_availability
    avail = check_semantic_model_availability()
    assert isinstance(avail, dict)
    assert avail["available"] is True


def test_database_integrity_check():
    """Verify SQLite database passes PRAGMA quick_check."""
    from app.services.db_health_service import run_quick_check
    res = run_quick_check()
    assert res["success"] is True
    assert res["is_clean"] is True
