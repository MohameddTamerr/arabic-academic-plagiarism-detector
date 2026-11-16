import hashlib
import json
import pytest
from tools.stage8h_runtime import verify_package


def test_package_checks_hash_mode_and_source(tmp_path):
    artifact=tmp_path/'test.jit'
    artifact.write_bytes(b'fixture only; never loaded')
    meta={'sha256':hashlib.sha256(artifact.read_bytes()).hexdigest(), 'mode':'int8','source_sha256':'source'}
    artifact.with_suffix('.manifest.json').write_text(json.dumps(meta),encoding='utf-8')
    assert verify_package(artifact,'source','int8') == meta
    with pytest.raises(ValueError): verify_package(artifact,'other','int8')
    with pytest.raises(ValueError): verify_package(artifact,'source','fp32')
    artifact.write_bytes(b'corrupt')
    with pytest.raises(ValueError): verify_package(artifact,'source','int8')


def test_missing_package_fails(tmp_path):
    with pytest.raises(FileNotFoundError): verify_package(tmp_path/'missing.jit','source','int8')
