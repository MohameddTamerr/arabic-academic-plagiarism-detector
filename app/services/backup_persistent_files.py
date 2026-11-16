"""Snapshot and restore database-referenced source files without rewriting reports."""
import hashlib
import json
import ntpath
import os
import re
import shutil
import sqlite3
from pathlib import Path, PurePosixPath
from contextlib import closing

import config


TABLES = ('reports', 'documents', 'thesis_parts', 'research_files')


def references(database):
    refs=[]
    with closing(sqlite3.connect(str(database))) as conn:
        for table in TABLES:
            columns={row[1] for row in conn.execute(f'PRAGMA table_info({table})')}
            if not {'id','file_path'} <= columns:continue
            status='storage_status' if table=='research_files' and 'storage_status' in columns else "''"
            expected='file_hash' if table in ('research_files','documents') and 'file_hash' in columns else "''"
            report_payload='report_json' if table=='reports' and 'report_json' in columns else "''"
            for row in conn.execute(f'SELECT id, file_path, {status}, {expected}, {report_payload} FROM {table} WHERE file_path IS NOT NULL AND file_path != ?',('',)):
                if row[2]=='registry_only':continue
                expected_hash=row[3] or ''
                if table=='reports' and row[4]:
                    try:expected_hash=json.loads(row[4]).get('source_sha256','') or ''
                    except (AttributeError,TypeError,ValueError):raise ValueError(f'Invalid report metadata: {row[0]}')
                refs.append({'table':table,'id':str(row[0]),'original_path':str(row[1]),'expected_sha256':expected_hash})
        columns={row[1] for row in conn.execute('PRAGMA table_info(reports)')}
        if {'id','report_json'} <= columns:
            for report_id,payload in conn.execute('SELECT id,report_json FROM reports WHERE report_json IS NOT NULL'):
                try:data=json.loads(payload or '{}')
                except (TypeError,ValueError):raise ValueError(f'Invalid report metadata: {report_id}')
                if not isinstance(data,dict):raise ValueError(f'Invalid report metadata: {report_id}')
                for index,item in enumerate(data.get('files') or []):
                    if not isinstance(item,dict):continue
                    for field in ('path','file_path'):
                        if isinstance(item.get(field),str) and item[field]:
                            refs.append({'table':'reports_json','id':f'{report_id}:{index}:{field}','original_path':item[field],'expected_sha256':''})
                if isinstance(data.get('final_file_path'),str) and data['final_file_path']:
                    refs.append({'table':'reports_json','id':f'{report_id}:final_file_path','original_path':data['final_file_path'],'expected_sha256':''})
    return refs


def digest(path):
    h=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block);size+=len(block)
    return h.hexdigest(),size


def path_fingerprint(path):
    return hashlib.sha256(path.encode('utf-8',errors='surrogatepass')).hexdigest()


def stage(database, directory):
    """Fail closed for missing, external or changing files; retain only referenced files."""
    directory.mkdir(parents=True,exist_ok=True)
    allowed=[Path(config.STORAGE_ROOT).resolve(),Path(config.TEMP_UPLOAD_DIR).resolve()]
    refs=references(database);blobs={}
    with closing(sqlite3.connect(str(database))) as conn:
        has_map=conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='restored_source_paths'").fetchone()
        mappings={row[0]:(row[1],row[2]) for row in conn.execute('SELECT path_fingerprint,file_path,sha256 FROM restored_source_paths')} if has_map else {}
    for ref in refs:
        mapping=mappings.get(path_fingerprint(ref['original_path']))
        source=Path(mapping[0] if mapping else ref['original_path']).resolve()
        if not any(source.is_relative_to(root) for root in allowed):
            raise ValueError(f'Persistent source outside application storage: {ref["table"]} {ref["id"]}')
        if not source.is_file():raise FileNotFoundError(f'Missing persistent source: {ref["table"]} {ref["id"]}')
        before,size=digest(source)
        if mapping and mapping[1]!=before:
            raise ValueError(f'Restored source hash mismatch: {ref["table"]} {ref["id"]}')
        if ref['expected_sha256'] and ref['expected_sha256'].lower()!=before:
            raise ValueError(f'Persistent source hash mismatch: {ref["table"]} {ref["id"]}')
        target=directory/before
        if not target.exists():
            shutil.copyfile(source,target)
        copied,copied_size=digest(target)
        after,after_size=digest(source)
        if (before,size)!=(copied,copied_size) or (before,size)!=(after,after_size):
            raise ValueError(f'Persistent source changed during backup: {ref["table"]} {ref["id"]}')
        ref.update(sha256=before,size_bytes=size,basename=source.name,
                   path_fingerprint=path_fingerprint(ref.pop('original_path')))
        blobs[before]={'file_name':'persistent_files/'+before,'sha256':before,'size_bytes':size}
        cas=Path(config.STORAGE_ROOT)/'documents'/before[:2]/before[2:4]/before
        cas_content=cas/'content.bin';cas_metadata=cas/'metadata.json'
        if cas_content.exists() or cas_metadata.exists():
            if not cas.resolve().is_relative_to(Path(config.STORAGE_ROOT).resolve()):
                raise ValueError('Content-addressed source outside application storage')
            if not cas_content.resolve().is_relative_to(Path(config.STORAGE_ROOT).resolve()) or not cas_metadata.resolve().is_relative_to(Path(config.STORAGE_ROOT).resolve()):
                raise ValueError('Content-addressed file outside application storage')
            if not cas_content.is_file() or not cas_metadata.is_file() or digest(cas_content)!=(before,size):
                raise ValueError(f'Incomplete or corrupt content-addressed source: {before[:12]}')
            metadata_hash,metadata_size=digest(cas_metadata)
            with cas_metadata.open(encoding='utf-8') as stream:metadata=json.load(stream)
            if metadata.get('content_hash')!=before or metadata.get('size_bytes')!=size:
                raise ValueError(f'Invalid content-addressed metadata: {before[:12]}')
            if source.name=='content.bin' and source.resolve()==cas_content.resolve():
                extension=metadata.get('extension','').lower()
                if extension in ('.pdf','.docx'):
                    ref['basename']='content'+extension
            metadata_target=directory/metadata_hash
            if not metadata_target.exists():shutil.copyfile(cas_metadata,metadata_target)
            if digest(metadata_target)!=(metadata_hash,metadata_size) or digest(cas_metadata)!=(metadata_hash,metadata_size):
                raise ValueError('Content-addressed metadata changed during backup')
            blobs[metadata_hash]={'file_name':'persistent_files/'+metadata_hash,'sha256':metadata_hash,'size_bytes':metadata_size}
            ref.update(cas_metadata_sha256=metadata_hash,cas_metadata_size=metadata_size)
    return {'name':'persistent_files','file_count':len(blobs),'size_bytes':sum(x['size_bytes'] for x in blobs.values()),'files':list(blobs.values()),'references':refs}


def safe_members(package):
    seen=set()
    reserved={'CON','PRN','AUX','NUL'} | {f'COM{i}' for i in range(1,10)} | {f'LPT{i}' for i in range(1,10)}
    for entry in package.infolist():
        name=entry.filename.replace('\\','/')
        pieces=name.rstrip('/').split('/')
        normalized='/'.join(pieces).casefold()
        if (not name or name.startswith('/') or ':' in name or
            any(not part or part in ('.','..') or part.endswith(('.', ' ')) or part.split('.')[0].upper() in reserved for part in pieces) or
            normalized in seen or ((entry.external_attr >> 16)&0o170000)==0o120000):
            raise ValueError('Unsafe or duplicate archive member')
        seen.add(normalized)


def validate_references(database, manifest):
    expected=references(database)
    component=next((x for x in manifest.get('components',[]) if x.get('name')=='persistent_files'),None)
    if component is None:
        # Preserve legacy archives only when every DB reference is represented
        # by one integrity-listed legacy member; missing sources fail closed.
        legacy={}
        for comp in manifest.get('components',[]):
            for item in comp.get('files',[]):
                name=item.get('file_name','').replace('\\','/')
                if name.startswith(('research_files/','reference_files/')) and len(PurePosixPath(name).parts)==2:
                    legacy.setdefault(PurePosixPath(name).name,[]).append(item)
        converted=[]
        for ref in expected:
            basename=ntpath.basename(ref['original_path'].replace('/','\\'))
            candidates=legacy.get(basename,[])
            if len(candidates)!=1:raise ValueError('Incomplete historical backup: persistent source documents are missing or ambiguous')
            item=candidates[0];sha=item.get('sha256','');size=item.get('size_bytes')
            if not re.fullmatch(r'[0-9a-f]{64}',sha) or not isinstance(size,int) or (ref['expected_sha256'] and ref['expected_sha256'].lower()!=sha):
                raise ValueError('Unverified historical source document')
            converted.append({'table':ref['table'],'id':ref['id'],'expected_sha256':ref['expected_sha256'],
                'path_fingerprint':path_fingerprint(ref['original_path']),'sha256':sha,'size_bytes':size,
                'basename':basename,'archive_file':item['file_name'].replace('\\','/')})
        return converted
    actual=component.get('references',[])
    expected_keys=[(r['table'],r['id'],path_fingerprint(r['original_path']),r['expected_sha256']) for r in expected]
    actual_keys=[(r.get('table'),str(r.get('id')),r.get('path_fingerprint'),r.get('expected_sha256') or '') for r in actual]
    if sorted(actual_keys)!=sorted(expected_keys):
        raise ValueError('Backup source references do not match its database')
    files={f.get('sha256'):f for f in component.get('files',[])}
    for ref in actual:
        sha=ref.get('sha256','');meta=files.get(sha)
        if not re.fullmatch(r'[0-9a-f]{64}',sha) or not meta or meta.get('file_name')!='persistent_files/'+sha or meta.get('size_bytes')!=ref.get('size_bytes') or (ref.get('expected_sha256') and ref['expected_sha256'].lower()!=sha):
            raise ValueError('Invalid persistent file manifest')
        name=ref.get('basename','')
        if not name or name in ('.','..') or ntpath.basename(name)!=name or '/' in name or '\\' in name or ':' in name:
            raise ValueError('Unsafe source filename')
        metadata_hash=ref.get('cas_metadata_sha256')
        if metadata_hash:
            metadata=files.get(metadata_hash)
            if not re.fullmatch(r'[0-9a-f]{64}',metadata_hash) or not metadata or metadata.get('file_name')!='persistent_files/'+metadata_hash or metadata.get('size_bytes')!=ref.get('cas_metadata_size'):
                raise ValueError('Invalid content-addressed metadata manifest')
    return actual


def rebase_staged_database(database, staging, destination, created_paths=None):
    """Create unique restored files and rebase database paths before replacing live DB."""
    manifest=json.loads((staging/'manifest.json').read_text(encoding='utf-8'))
    refs=validate_references(database,manifest)
    if not refs:return None
    if not destination.resolve().is_relative_to(Path(config.STORAGE_ROOT).resolve()):
        raise ValueError('Restore destination escapes application storage')
    destination.mkdir(parents=True,exist_ok=False)
    if created_paths is not None:created_paths.append(destination)
    with closing(sqlite3.connect(str(database))) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS restored_source_paths (path_fingerprint TEXT PRIMARY KEY, file_path TEXT NOT NULL, sha256 TEXT NOT NULL)')
        for ref in refs:
            blob=staging/ref.get('archive_file','persistent_files/'+ref['sha256'])
            if digest(blob)!=(ref['sha256'],ref['size_bytes']):raise ValueError('Corrupt staged persistent source')
            target=destination/ref['sha256']/ref['basename']
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copyfile(blob,target)
            if digest(target)!=(ref['sha256'],ref['size_bytes']):raise ValueError('Restored file verification failed')
            conn.execute('INSERT OR REPLACE INTO restored_source_paths(path_fingerprint,file_path,sha256) VALUES (?,?,?)',
                         (ref['path_fingerprint'],str(target),ref['sha256']))
            if ref['table'] in TABLES:
                conn.execute(f'UPDATE {ref["table"]} SET file_path=? WHERE id=?',
                             (str(target),ref['id']))
            metadata_hash=ref.get('cas_metadata_sha256')
            if metadata_hash:
                metadata_blob=staging/'persistent_files'/metadata_hash
                if digest(metadata_blob)!=(metadata_hash,ref['cas_metadata_size']):raise ValueError('Corrupt CAS metadata')
                with metadata_blob.open(encoding='utf-8') as stream:metadata=json.load(stream)
                if metadata.get('content_hash')!=ref['sha256'] or metadata.get('size_bytes')!=ref['size_bytes']:
                    raise ValueError('Invalid restored CAS metadata')
                cas_root=(Path(config.STORAGE_ROOT)/'documents').resolve()
                cas=(cas_root/ref['sha256'][:2]/ref['sha256'][2:4]/ref['sha256']).resolve()
                if not cas.is_relative_to(cas_root):raise ValueError('Unsafe CAS path')
                if cas.exists():
                    if not (cas/'content.bin').is_file() or not (cas/'metadata.json').is_file() or digest(cas/'content.bin')!=(ref['sha256'],ref['size_bytes']) or digest(cas/'metadata.json')!=(metadata_hash,ref['cas_metadata_size']):
                        raise ValueError('Existing content-addressed data conflicts with backup')
                else:
                    cas.parent.mkdir(parents=True,exist_ok=True);cas.mkdir(exist_ok=False)
                    shutil.copyfile(blob,cas/'content.bin');shutil.copyfile(metadata_blob,cas/'metadata.json')
                    if digest(cas/'content.bin')!=(ref['sha256'],ref['size_bytes']) or digest(cas/'metadata.json')!=(metadata_hash,ref['cas_metadata_size']):raise ValueError('CAS restore verification failed')
        conn.commit()
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored database failed integrity check')
    return destination
