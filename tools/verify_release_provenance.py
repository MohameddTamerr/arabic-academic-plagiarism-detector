"""Verify that a release manifest and checksum file describe one EXE exactly."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(artifact: Path, manifest_path: Path, checksums_path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    artifact = artifact.resolve()
    if not artifact.is_file():
        return False, [f"Artifact does not exist: {artifact}"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_meta = manifest.get("canonical_artifact", manifest.get("artifact", {}))
    expected_name = artifact_meta.get("filename")
    expected_size = artifact_meta.get("size_bytes")
    expected_hash = str(artifact_meta.get("sha256", "")).lower()
    actual_hash = sha256_file(artifact)

    if expected_name != artifact.name:
        errors.append(f"Manifest filename mismatch: {expected_name!r} != {artifact.name!r}")
    if expected_size != artifact.stat().st_size:
        errors.append(f"Manifest size mismatch: {expected_size!r} != {artifact.stat().st_size!r}")
    if expected_hash != actual_hash:
        errors.append(f"Manifest SHA-256 mismatch: {expected_hash!r} != {actual_hash!r}")

    checksum_entries: dict[str, str] = {}
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, name = line.partition("  ")
        checksum_entries[name.replace("/", "\\")] = digest.lower()
    expected_checksum = checksum_entries.get(artifact.name)
    if expected_checksum != actual_hash:
        errors.append(f"SHA256SUMS mismatch: {expected_checksum!r} != {actual_hash!r}")
    return not errors, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("checksums", type=Path)
    args = parser.parse_args()
    ok, errors = verify(args.artifact, args.manifest, args.checksums)
    if ok:
        print("PASS: artifact, manifest, and SHA256SUMS match exactly")
        return 0
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
