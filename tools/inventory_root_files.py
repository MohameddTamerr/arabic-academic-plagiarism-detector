# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path

root = Path('.').resolve()
root_files = [f for f in root.iterdir() if f.is_file()]

# Check git status for tracked vs untracked
res = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
git_untracked = set()
git_modified = set()
for line in res.stdout.splitlines():
    status = line[:2]
    fname = line[3:].strip().replace('"', '')
    if '?' in status:
        git_untracked.add(fname)
    else:
        git_modified.add(fname)

# Check references in python files, spec files, and bat files
code_files = list(root.glob('app/**/*.py')) + list(root.glob('tools/**/*.py')) + list(root.glob('plagiarism_detector/**/*.py')) + list(root.glob('*.spec')) + list(root.glob('*.py'))

def is_referenced(fname):
    fname_str = fname.name
    for cf in code_files:
        if cf == fname: continue
        try:
            with open(cf, 'r', encoding='utf-8', errors='ignore') as fp:
                if fname_str in fp.read():
                    return True, cf.relative_to(root)
        except:
            pass
    return False, None

print(f"Total root files: {len(root_files)}\n")
for f in sorted(root_files, key=lambda x: x.name.lower()):
    sz = f.stat().st_size
    if sz > 1024*1024: sz_str = f"{sz/(1024*1024):.2f} MB"
    elif sz > 1024: sz_str = f"{sz/1024:.2f} KB"
    else: sz_str = f"{sz} B"

    rel_name = f.name
    tracked = "UNTRACKED" if rel_name in git_untracked else ("MODIFIED" if rel_name in git_modified else "TRACKED")
    ref, by = is_referenced(f)
    ref_str = f"Referenced by {by}" if ref else "NOT directly referenced in code"
    print(f"{rel_name:<45} | {sz_str:<10} | {tracked:<10} | {ref_str}")
