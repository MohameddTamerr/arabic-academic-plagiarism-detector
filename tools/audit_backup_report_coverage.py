"""Read-only check for report source documents missing from a backup archive.

This is a coverage diagnostic, not a substitute for backup integrity validation.
"""
import argparse
import hashlib
import json
import ntpath
import sqlite3
import shutil
import tempfile
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile


def inspect(archive):
    with ZipFile(archive) as package, tempfile.TemporaryDirectory(prefix='backup-audit-') as directory:
        names=set(package.namelist())
        path=Path(directory)/'papers.db'
        for name in ('papers.db','papers.db-wal','papers.db-shm'):
            member='database/'+name
            if member in names:
                with package.open(member) as source,(Path(directory)/name).open('wb') as dest:
                    shutil.copyfileobj(source,dest,length=1024*1024)
        if not path.is_file():raise ValueError('Backup has no database/papers.db')
        with closing(sqlite3.connect(str(path))) as database:
            reports=database.execute('select id,file_path from reports where file_path is not null and file_path != ?',('',)).fetchall()
        try:
            manifest=json.loads(package.read('manifest.json'))
        except (KeyError,ValueError):
            raise ValueError('Backup has no readable manifest')
        component=next((c for c in manifest.get('components',[]) if c.get('name')=='persistent_files'),None)
        refs={(str(r.get('id')),r.get('path_fingerprint')):r for r in (component or {}).get('references',[]) if r.get('table')=='reports'}
        missing=[]
        for report_id, source in reports:
            basename=ntpath.basename(source.replace('/','\\'))
            fingerprint=hashlib.sha256(source.encode('utf-8',errors='surrogatepass')).hexdigest()
            ref=refs.get((str(report_id),fingerprint))
            in_new_format=bool(ref and 'persistent_files/'+str(ref.get('sha256','')) in names)
            if not in_new_format and 'research_files/'+basename not in names and 'report_files/'+basename not in names:
                missing.append(str(report_id))
        return {'report_files_expected':len(reports),'missing_report_ids':missing,
                'coverage_complete':not missing,'note':'Names only; does not verify source hashes, paths or restore behavior.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive',type=Path)
    outcome=inspect(parser.parse_args().archive)
    print(json.dumps(outcome,indent=2))
    raise SystemExit(0 if outcome['coverage_complete'] else 1)
