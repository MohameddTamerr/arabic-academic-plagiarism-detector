"""Freeze a side-by-side candidate input snapshot; never touch old releases/data."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()


def freeze(destination):
    root=Path(__file__).resolve().parents[1]
    destination=destination.resolve()
    if destination==root or destination in root.parents:
        raise ValueError('Snapshot must not replace workspace or its parents')
    destination.mkdir(parents=True,exist_ok=False)
    names=['config.py','server.py','run_app.py','release_manifest.json','requirements-stage8m-research.txt',
           'Police-Academy-College-of-Graduate-Studies.png','scratch/app.ico']
    files=[root/name for name in names]
    candidate_manifest = root / 'release_source_manifest.json'
    if candidate_manifest.is_file():
        files.append(candidate_manifest)
    for folder in ('app','plagiarism_detector','templates','static','tools','tests','assets','models','vendor'):
        files.extend(p for p in (root/folder).rglob('*') if p.is_file()
            and not any(part in ('__pycache__','.locks') for part in p.relative_to(root).parts)
            and p.suffix not in ('.pyc','.pyo'))
    records={}
    for source in sorted(set(files)):
        relative=source.relative_to(root)
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
        digest=sha(target)
        if digest!=sha(source):raise RuntimeError(f'Input changed while freezing: {relative}')
        records[relative.as_posix()]={'sha256':digest,'bytes':target.stat().st_size}
    manifest={'purpose':'Unapproved Stage 8L validation candidate, not historical release',
        'git_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
        'review':'Candidate-only source/config/packaging review and separately recorded tests; no production approval',
        'excludes':'Production databases, user storage, credentials, backups, historical executables, research AI weights',
        'files':records}
    (destination/'STAGE8L_SOURCE_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    destination=parser.parse_args().destination.resolve()
    manifest = freeze(destination)
    records = manifest['files']
    print(json.dumps({'snapshot':str(destination),'files':len(records),'manifest_sha256':sha(destination/'STAGE8L_SOURCE_MANIFEST.json')}))


if __name__=='__main__':main()
