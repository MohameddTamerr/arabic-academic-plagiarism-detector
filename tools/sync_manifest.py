# -*- coding: utf-8 -*-
import json
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parent.parent
manifest_path = root / 'release_source_manifest.json'
with open(manifest_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

hashes = data['critical_file_hashes_sha256']
updated = []
for rel_path in hashes:
    p = root / rel_path
    if p.exists():
        new_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        if new_hash != hashes[rel_path]:
            updated.append((rel_path, hashes[rel_path][:8], new_hash[:8]))
            hashes[rel_path] = new_hash

with open(manifest_path, 'w', encoding='utf-8', newline='') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print(f'Updated {len(updated)} hashes:')
for u in updated:
    print(f'  {u[0]}: {u[1]} -> {u[2]}')
