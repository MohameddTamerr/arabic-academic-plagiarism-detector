import hashlib
import io
import json
import shutil
import sqlite3
import zipfile
from pathlib import Path

import pytest
import config
from app import create_app
from app.repositories import base_repo, report_repo, backup_repo
from app.routes import scan_routes
from app.services import backup_service, backup_persistent_files


@pytest.fixture
def isolated_source(monkeypatch,tmp_path):
    from app.services import scan_service

    # Prior Flask tests can leave accepted scans running against the suite DB.
    scan_service.drain_scan_executor(timeout=30)
    scan_service.resume_scan_executor()
    old_url=config.DATABASE_URL
    context=pytest.MonkeyPatch()
    storage=tmp_path/'source_storage';uploads=storage/'uploads';backups=storage/'backups'
    uploads.mkdir(parents=True);backups.mkdir()
    db=tmp_path/'source_test.db'
    context.setattr(config,'STORAGE_ROOT',storage)
    context.setattr(config,'TEMP_UPLOAD_DIR',uploads)
    context.setattr(config,'BACKUP_DIR',backups)
    context.setattr(config,'DEFAULT_SQLITE_PATH',db)
    context.setattr(scan_routes,'get_current_settings',lambda:{**config.DEFAULT_SETTINGS,'enable_semantic_model':False})
    base_repo.rebind_engine('sqlite:///'+db.as_posix());base_repo.init_database()
    try:yield context,storage,uploads,backups,db
    finally:
        context.undo();base_repo.rebind_engine(old_url)


def make_document_fixtures():
    import fitz
    from docx import Document
    text='تتناول هذه الدراسة تحليل البيانات وتوثيق المصادر العلمية ومراجعة النتائج '
    pdf=fitz.open();page=pdf.new_page()
    page.insert_htmlbox(fitz.Rect(40,40,550,780),'<div dir="rtl">'+text*5+'</div>')
    data=pdf.tobytes();pdf.close()
    doc=Document();doc.add_paragraph(text*5);buf=io.BytesIO();doc.save(buf)
    return [('source.pdf',data),('source.docx',buf.getvalue())]


def test_backup_restore_reopens_both_documents_in_separate_storage(isolated_source,tmp_path):
    m,storage,uploads,backups,db=isolated_source
    from app.services import document_preview_service
    from docx import Document
    import fitz

    def convert_fixture(source, destination):
        text = ' '.join(paragraph.text for paragraph in Document(source).paragraphs)
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_htmlbox(fitz.Rect(40, 40, 550, 780), f'<div dir="rtl">{text}</div>')
            pdf.save(destination)

    # Exercise restored originals and the cache/preview path independently of Word COM.
    m.setattr(document_preview_service, '_convert_with_word', convert_fixture)
    app=create_app();app.config['TESTING']=True
    ids=[];hashes={};original_paths={};fixture_data={}
    with app.test_client() as client:
        for name,data in make_document_fixtures():
            response=client.post('/api/analyze',data={'file':(io.BytesIO(data),name)},content_type='multipart/form-data')
            assert response.status_code==200,response.get_json()
            body=response.get_json();ids.append(body['id']);hashes[body['id']]=hashlib.sha256(data).hexdigest()
            original_paths[body['id']]=body['file_path'];fixture_data[body['id']]=data
            assert body['ai_analysis']['status']=='unavailable'
    from app.storage.filesystem_backend import FileSystemStorageBackend
    FileSystemStorageBackend(storage).put(fixture_data[ids[0]],hashes[ids[0]],ext='.pdf')
    with sqlite3.connect(str(db)) as conn:
        raw=conn.execute('select report_json from reports where id=?',(ids[0],)).fetchone()[0]
        payload=json.loads(raw);payload['files']=[{'path':original_paths[ident]} for ident in ids]
        original_payload=json.dumps(payload,ensure_ascii=False)
        conn.execute('update reports set report_json=? where id=?',(original_payload,ids[0]));conn.commit()
    result=backup_service.create_institutional_backup(created_by='test')
    archive=Path(result['file_path']);assert backup_service.validate_backup_package_file(archive)['valid']
    with zipfile.ZipFile(archive) as z:
        manifest=json.loads(z.read('manifest.json'))
        component=next(c for c in manifest['components'] if c['name']=='persistent_files')
        assert {r['id'] for r in component['references'] if r['table']=='reports'} >= set(ids)
        assert all('original_path' not in r for r in component['references'])
        assert all('persistent_files/'+digest in z.namelist() for digest in hashes.values())
        assert any(r.get('cas_metadata_sha256') for r in component['references'])
    for path in original_paths.values():Path(path).unlink()
    second=tmp_path/'restore_storage';second_uploads=second/'uploads';second_backups=second/'backups'
    second_uploads.mkdir(parents=True);second_backups.mkdir()
    second_db=tmp_path/'restore_test.db';shutil.copy2(archive,second_backups/archive.name)
    archive_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
    m.setattr(config,'STORAGE_ROOT',second);m.setattr(config,'TEMP_UPLOAD_DIR',second_uploads)
    m.setattr(config,'BACKUP_DIR',second_backups);m.setattr(config,'DEFAULT_SQLITE_PATH',second_db)
    base_repo.rebind_engine('sqlite:///'+second_db.as_posix());base_repo.init_database()
    restored=backup_service.restore_institutional_backup(result['backup_identifier'],result['backup_identifier'])
    assert restored['success']
    assert hashlib.sha256((second_backups/archive.name).read_bytes()).hexdigest()==archive_hash
    with sqlite3.connect(str(second_db)) as conn:
        assert conn.execute('pragma integrity_check').fetchone()[0]=='ok'
        assert conn.execute('select report_json from reports where id=?',(ids[0],)).fetchone()[0]==original_payload
    cas=second/'documents'/hashes[ids[0]][:2]/hashes[ids[0]][2:4]/hashes[ids[0]]
    assert (cas/'content.bin').read_bytes()==fixture_data[ids[0]]
    assert json.loads((cas/'metadata.json').read_text(encoding='utf-8'))['content_hash']==hashes[ids[0]]
    with app.test_client() as client:
        for ident in ids:
            report=report_repo.get_report(ident);path=Path(report['file_path'])
            assert path.is_relative_to(second) and hashlib.sha256(path.read_bytes()).hexdigest()==hashes[ident]
            assert client.get('/api/reports/'+ident).status_code==200
            suffix='?file_index=0' if ident==ids[0] else ''
            assert client.get('/api/pdf/report/'+ident+'/info'+suffix).status_code==200
            assert client.get('/api/pdf/report/'+ident+'/highlights?page=1'+('&file_index=0' if suffix else '')).status_code==200
        assert client.get('/api/pdf/report/'+ids[0]+'/info?file_index=1').status_code==200
    new_backup=backup_service.create_institutional_backup(created_by='after_restore')
    assert backup_service.validate_backup_package_file(Path(new_backup['file_path']))['valid']
    base_repo.rebind_engine('sqlite:///'+second_db.as_posix())
    assert all(report_repo.get_report(ident) for ident in ids)


def test_complete_legacy_archive_references_remain_supported(tmp_path):
    db=tmp_path/'legacy.db';source_path=r'C:\old\uploads\legacy.pdf'
    sha=hashlib.sha256(b'document').hexdigest()
    with sqlite3.connect(db) as conn:
        conn.execute('create table research_files (id integer primary key,file_path text,storage_status text,file_hash text)')
        conn.execute('insert into research_files values (?,?,?,?)',(1,source_path,'finalized',sha));conn.commit()
    manifest={'components':[{'name':'research_files','files':[{'file_name':'research_files/legacy.pdf','sha256':sha,'size_bytes':8}]}]}
    refs=backup_persistent_files.validate_references(db,manifest)
    assert len(refs)==1 and refs[0]['archive_file']=='research_files/legacy.pdf'


def test_missing_source_fails_backup(isolated_source):
    _,_,uploads,_,_=isolated_source
    missing=uploads/'missing.pdf'
    report_repo.save_report(report_id='missing1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'missing1'},file_path=str(missing))
    with pytest.raises(FileNotFoundError):backup_service.create_institutional_backup(created_by='test')


def test_source_changed_after_report_is_rejected(isolated_source):
    _,_,uploads,_,_=isolated_source
    source=uploads/'changed_after_scan.pdf';source.write_bytes(b'original at report save')
    report_repo.save_report(report_id='changed2',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'changed2'},file_path=str(source))
    source.write_bytes(b'modified after report save')
    with pytest.raises(ValueError,match='hash mismatch'):
        backup_service.create_institutional_backup(created_by='test')


def test_replacing_report_document_updates_its_integrity_hash(isolated_source):
    _,_,uploads,_,_=isolated_source
    old=uploads/'old.pdf';old.write_bytes(b'old')
    new=uploads/'new.pdf';new.write_bytes(b'new')
    report_repo.save_report(report_id='replace1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'replace1'},file_path=str(old))
    report_repo.update_report_latest_pdf('replace1',str(new),'updated text')
    report=report_repo.get_report('replace1')
    assert report['source_sha256']==hashlib.sha256(b'new').hexdigest()
    archive=backup_service.create_institutional_backup(created_by='test')
    assert backup_service.validate_backup_package_file(Path(archive['file_path']))['valid']


def test_cas_content_path_recovers_correct_document_extension(isolated_source,tmp_path):
    m,storage,_,_,db=isolated_source
    from app.storage.filesystem_backend import FileSystemStorageBackend
    original=b'synthetic pdf contents';sha=hashlib.sha256(original).hexdigest()
    stored=FileSystemStorageBackend(storage).put(original,sha,ext='.pdf')
    report_repo.save_report(report_id='cas1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'cas1'},file_path=stored['file_path'])
    staging=tmp_path/'staged';staging.mkdir();snapshot=staging/'db.sqlite'
    backup_service.backup_sqlite_consistently(db,snapshot)
    component=backup_persistent_files.stage(snapshot,staging/'persistent_files')
    (staging/'manifest.json').write_text(json.dumps({'components':[component]}),encoding='utf-8')
    second=tmp_path/'second_storage';second.mkdir();m.setattr(config,'STORAGE_ROOT',second)
    destination=second/'restored_sources';backup_persistent_files.rebase_staged_database(snapshot,staging,destination)
    with sqlite3.connect(snapshot) as conn:path=Path(conn.execute('select file_path from reports where id=?',('cas1',)).fetchone()[0])
    assert path.suffix=='.pdf' and path.read_bytes()==original
    cas=second/'documents'/sha[:2]/sha[2:4]/sha
    assert (cas/'content.bin').read_bytes()==original and (cas/'metadata.json').is_file()


def test_incomplete_historical_backup_is_rejected(isolated_source,tmp_path):
    _,_,uploads,_,_=isolated_source
    source=uploads/'legacy.pdf';source.write_bytes(b'legacy fixture')
    report_repo.save_report(report_id='legacy1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'legacy1'},file_path=str(source))
    archive=Path(backup_service.create_institutional_backup(created_by='test')['file_path'])
    legacy=tmp_path/'legacy_incomplete.zip'
    with zipfile.ZipFile(archive) as old,zipfile.ZipFile(legacy,'w') as new:
        manifest=json.loads(old.read('manifest.json'))
        manifest['components']=[c for c in manifest['components'] if c['name']!='persistent_files']
        for item in old.infolist():
            if item.filename.startswith('persistent_files/'):continue
            new.writestr(item.filename,json.dumps(manifest).encode() if item.filename=='manifest.json' else old.read(item.filename))
    assert not backup_service.validate_backup_package_file(legacy)['valid']


def test_creating_catalog_entry_is_not_accepted_as_completed(isolated_source):
    backup=backup_service.create_institutional_backup(created_by='test')
    assert backup_repo.update_backup_status(backup['backup_identifier'],'creating')
    assert not backup_service.validate_backup(backup['backup_identifier'])['valid']


def test_changed_source_during_snapshot_fails(isolated_source,monkeypatch):
    _,_,uploads,_,db=isolated_source
    path=uploads/'source.pdf';path.write_bytes(b'original')
    report_repo.save_report(report_id='changed1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'changed1'},file_path=str(path))
    copy=backup_persistent_files.shutil.copyfile
    def change(source,target,*args,**kwargs):
        result=copy(source,target,*args,**kwargs)
        if Path(source)==path:path.write_bytes(b'changed')
        return result
    monkeypatch.setattr(backup_persistent_files.shutil,'copyfile',change)
    with pytest.raises(ValueError,match='changed during backup'):
        backup_persistent_files.stage(db,uploads/'staging_fixture')


def test_interrupted_invalid_and_unsafe_archives_rejected(tmp_path):
    partial=tmp_path/'interrupted.partial';partial.write_bytes(b'not a complete backup')
    assert not backup_service.validate_backup_package_file(partial)['valid']
    invalid=tmp_path/'invalid.zip';invalid.write_bytes(b'not zip')
    assert not backup_service.validate_backup_package_file(invalid)['valid']
    unsafe=tmp_path/'unsafe.zip'
    with zipfile.ZipFile(unsafe,'w') as z:z.writestr('../escape.txt','bad')
    assert not backup_service.validate_backup_package_file(unsafe)['valid']
    assert not (tmp_path.parent/'escape.txt').exists()


def test_archive_missing_corrupt_source_or_database_is_rejected(isolated_source,tmp_path):
    _,_,uploads,_,_=isolated_source
    path=uploads/'fixture.pdf';path.write_bytes(b'original fixture')
    report_repo.save_report(report_id='tamper1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'tamper1'},file_path=str(path))
    archive=Path(backup_service.create_institutional_backup(created_by='test')['file_path'])
    with zipfile.ZipFile(archive) as original:
        manifest=json.loads(original.read('manifest.json'))
        component=next(c for c in manifest['components'] if c['name']=='persistent_files')
        blob=component['files'][0]['file_name']
        for mode in ('missing','corrupt','database','settings','metadata','traversal','alias','case_alias','wal'):
            changed=tmp_path/(mode+'.zip')
            with zipfile.ZipFile(changed,'w') as z:
                for item in original.infolist():
                    if mode=='missing' and item.filename==blob:continue
                    data=original.read(item.filename)
                    if mode=='corrupt' and item.filename==blob:data=b'corrupt'
                    if mode=='database' and item.filename=='database/papers.db':data=b'corrupt database'
                    if mode=='settings' and item.filename=='configuration/settings.json':data=b'{}'
                    if mode=='metadata' and item.filename=='metadata/version_info.json':data=b'{}'
                    z.writestr(item.filename,data)
                if mode=='traversal':z.writestr('../escape.txt','bad')
                if mode=='alias':z.writestr('database/./papers.db','bad')
                if mode=='case_alias':z.writestr('DATABASE/PAPERS.DB','bad')
                if mode=='wal':z.writestr('database/papers.db-wal','unchecked data')
            assert not backup_service.validate_backup_package_file(changed)['valid'],mode
    partial=tmp_path/'complete_but_interrupted.partial';shutil.copy2(archive,partial)
    assert not backup_service.validate_backup_package_file(partial)['valid']


def test_disk_failure_does_not_replace_source_or_create_completed_archive(isolated_source,monkeypatch):
    _,_,uploads,backups,_=isolated_source
    source=uploads/'original.pdf';source.write_bytes(b'original')
    report_repo.save_report(report_id='diskfull1',title='test',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'diskfull1'},file_path=str(source))
    def no_space(*args,**kwargs):raise OSError('simulated disk full')
    monkeypatch.setattr(backup_persistent_files.shutil,'copyfile',no_space)
    with pytest.raises(OSError):backup_service.create_institutional_backup(created_by='test')
    assert source.read_bytes()==b'original'
    assert not list(backups.glob('*.zip')) and not list(backups.glob('*.partial'))


def test_failed_restore_preserves_existing_database_and_files(isolated_source,tmp_path,monkeypatch):
    m,_,uploads,_,_=isolated_source
    source=uploads/'source.pdf';source.write_bytes(b'backup document')
    report_repo.save_report(report_id='newreport',title='from backup',overall_pct=0,copied_pct=0,para_pct=0,
        report_dict={'id':'newreport'},file_path=str(source))
    backup=backup_service.create_institutional_backup(created_by='test')
    original_archive=Path(backup['file_path']);archive_hash=hashlib.sha256(original_archive.read_bytes()).hexdigest()
    second=tmp_path/'existing_storage';second_uploads=second/'uploads';second_backups=second/'backups'
    second_uploads.mkdir(parents=True);second_backups.mkdir()
    copied_archive=second_backups/original_archive.name;shutil.copy2(original_archive,copied_archive)
    second_db=tmp_path/'existing_test.db'
    m.setattr(config,'STORAGE_ROOT',second);m.setattr(config,'TEMP_UPLOAD_DIR',second_uploads)
    m.setattr(config,'BACKUP_DIR',second_backups);m.setattr(config,'DEFAULT_SQLITE_PATH',second_db)
    base_repo.rebind_engine('sqlite:///'+second_db.as_posix());base_repo.init_database()
    existing=second_uploads/'existing.pdf';existing.write_bytes(b'keep this document')
    report_repo.save_report(report_id='existing1',title='existing',overall_pct=7,copied_pct=0,para_pct=0,
        report_dict={'id':'existing1'},file_path=str(existing))
    original_copy=backup_persistent_files.shutil.copyfile
    def fail_restore(source,target,*args,**kwargs):
        if 'persistent_files' in Path(source).parts and any(part.startswith('_staging_restore_') for part in Path(source).parts):
            raise OSError('simulated restore disk full')
        return original_copy(source,target,*args,**kwargs)
    monkeypatch.setattr(backup_persistent_files.shutil,'copyfile',fail_restore)
    with pytest.raises(RuntimeError,match='simulated restore disk full'):
        backup_service.restore_institutional_backup(backup['backup_identifier'],backup['backup_identifier'])
    assert existing.read_bytes()==b'keep this document'
    assert report_repo.get_report('existing1')['overall_pct']==7
    assert report_repo.get_report('newreport') is None
    assert hashlib.sha256(copied_archive.read_bytes()).hexdigest()==archive_hash


def test_post_database_failure_rolls_back_existing_data(isolated_source,tmp_path,monkeypatch):
    m,_,uploads,_,_=isolated_source
    source=uploads/'incoming.pdf';source.write_bytes(b'incoming')
    report_repo.save_report(report_id='incoming1',title='incoming',overall_pct=1,copied_pct=0,para_pct=0,
        report_dict={'id':'incoming1'},file_path=str(source))
    backup=backup_service.create_institutional_backup(created_by='test')
    second=tmp_path/'rollback_storage';second_uploads=second/'uploads';second_backups=second/'backups'
    second_uploads.mkdir(parents=True);second_backups.mkdir()
    shutil.copy2(backup['file_path'],second_backups/Path(backup['file_path']).name)
    second_db=tmp_path/'rollback_test.db'
    m.setattr(config,'STORAGE_ROOT',second);m.setattr(config,'TEMP_UPLOAD_DIR',second_uploads)
    m.setattr(config,'BACKUP_DIR',second_backups);m.setattr(config,'DEFAULT_SQLITE_PATH',second_db)
    base_repo.rebind_engine('sqlite:///'+second_db.as_posix());base_repo.init_database()
    existing=second_uploads/'existing.pdf';existing.write_bytes(b'existing')
    report_repo.save_report(report_id='existing2',title='existing',overall_pct=7,copied_pct=0,para_pct=0,
        report_dict={'id':'existing2'},file_path=str(existing))
    def fail(*args,**kwargs):raise RuntimeError('simulated post-database failure')
    monkeypatch.setattr(backup_repo,'mark_backup_restored',fail)
    with pytest.raises(RuntimeError,match='simulated post-database failure'):
        backup_service.restore_institutional_backup(backup['backup_identifier'],backup['backup_identifier'])
    assert existing.read_bytes()==b'existing'
    assert report_repo.get_report('existing2')['overall_pct']==7
    assert report_repo.get_report('incoming1') is None
    with sqlite3.connect(str(second_db)) as db:assert db.execute('pragma integrity_check').fetchone()[0]=='ok'
