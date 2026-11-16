import hashlib
import json

from tools.verify_release_provenance import verify


def test_verify_release_provenance_requires_exact_artifact_metadata(tmp_path):
    artifact = tmp_path / "Arabic-Plagiarism-System-RC3.exe"
    artifact.write_bytes(b"canonical release")
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest = tmp_path / "RELEASE_MANIFEST.json"
    manifest.write_text(
        json.dumps(
            {
                "canonical_artifact": {
                    "filename": artifact.name,
                    "size_bytes": artifact.stat().st_size,
                    "sha256": digest,
                }
            }
        ),
        encoding="utf-8",
    )
    checksums = tmp_path / "SHA256SUMS.txt"
    checksums.write_text(f"{digest}  {artifact.name}\n", encoding="utf-8")

    assert verify(artifact, manifest, checksums) == (True, [])

    manifest.write_text(
        json.dumps({"canonical_artifact": {"filename": "wrong.exe", "size_bytes": 0, "sha256": "0" * 64}}),
        encoding="utf-8",
    )
    ok, errors = verify(artifact, manifest, checksums)
    assert ok is False
    assert len(errors) == 3
