"""Freeze and build a side-by-side Windows CPU release candidate."""

import argparse
from datetime import datetime, timezone
from importlib.metadata import distributions, version
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from tools.stage8l_freeze_candidate import freeze
from tools.verify_release_provenance import sha256_file, verify


EXE_NAME = 'Arabic-Plagiarism-System-Windows8GB-RC'


def write_json(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def package(output):
    if sys.platform != 'win32' or platform.machine().upper() != 'AMD64' or sys.version_info[:2] != (3, 13):
        raise ValueError('Use the Windows AMD64 CPython 3.13 build environment matching vendor DLLs.')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'source'
    snapshot = freeze(source)
    source_manifest = source / 'STAGE8L_SOURCE_MANIFEST.json'
    metadata_dir = output / 'metadata'
    metadata_dir.mkdir()
    metadata = metadata_dir / 'release_manifest.json'
    release_source = json.loads((source / 'release_source_manifest.json').read_bytes())
    critical_hashes = release_source['critical_file_hashes_sha256']
    mismatches = [name for name, digest in critical_hashes.items()
                  if snapshot['files'].get(name, {}).get('sha256') != digest]
    if not critical_hashes or mismatches:
        raise ValueError(f'Release source manifest does not match the frozen inputs: {mismatches}')
    vendor_versions = {item.metadata['Name'].lower(): item.version for item in
                       distributions(path=[str(source / 'vendor')]) if item.metadata['Name']}
    core_versions = {
        name: vendor_versions[name] if name in vendor_versions else version(name)
        for name in ('pyinstaller', 'flask', 'sqlalchemy', 'waitress', 'onnxruntime', 'fastembed',
                     'numpy', 'scipy', 'scikit-learn')
    }
    manifest = {
        'release_version': release_source['release_version'],
        'build_timestamp': datetime.now(timezone.utc).isoformat(),
        'application_version': release_source['application_version'],
        'engine_version': release_source['engine_version'],
        'readiness_verdict': 'Windows validation candidate. Target 8 GB acceptance pending.',
        'ai_validation_status': 'no_validated_model',
        'git_head': snapshot['git_head'],
        'source_manifest_sha256': sha256_file(source_manifest),
        'build_environment': {'platform': platform.platform(), 'python': platform.python_version(),
                              **core_versions},
        'critical_file_hashes_sha256': critical_hashes,
    }
    write_json(metadata, manifest)
    subprocess.run([
        sys.executable, '-c',
        'from pathlib import Path; import sys; from tools.build_single_exe import build_single_exe; '
        'build_single_exe(output_name=sys.argv[1], dist_dir=Path(sys.argv[2]), '
        'manifest_file=Path(sys.argv[3]), terminate_running=False)',
        EXE_NAME, str(output), str(metadata),
    ], cwd=source, env={**os.environ, 'ARABIC_APP_DATA_DIR': str(output / 'build-data'),
                        'PYINSTALLER_CONFIG_DIR': str(output / 'pyinstaller-cache')}, check=True)

    exe = output / f'{EXE_NAME}.exe'
    digest = sha256_file(exe)
    manifest['canonical_artifact'] = {'filename': exe.name, 'size_bytes': exe.stat().st_size, 'sha256': digest}
    final_manifest = output / 'RELEASE_MANIFEST.json'
    checksums = output / 'SHA256SUMS.txt'
    write_json(final_manifest, manifest)
    with checksums.open('x', encoding='ascii') as stream:
        stream.write(f'{digest}  {exe.name}\n')
    ok, errors = verify(exe, final_manifest, checksums)
    if not ok:
        raise RuntimeError('; '.join(errors))
    print(f'Verified candidate: {exe}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New directory for the build and verification files')
    package(parser.parse_args().output)
