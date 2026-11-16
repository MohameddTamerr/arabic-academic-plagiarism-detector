"""Opt-in local Word lifecycle probe using generated authorized documents."""
import hashlib
import json
import os
import time
import pytest


@pytest.mark.skipif(os.environ.get('RUN_STAGE8K_WORD')!='1',reason='requires local Windows Word installation')
@pytest.mark.parametrize('trial',range(3))
def test_real_word_conversion_releases_files(tmp_path,trial):
    import psutil
    import fitz
    from docx import Document
    from app.services.document_preview_service import _convert_with_word
    def word_processes():
        return [p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='winword.exe']
    before=word_processes()
    source=tmp_path/'original.docx';destination=tmp_path/'converted.pdf'
    document=Document();document.add_paragraph('دراسة أكاديمية لاختبار تحرير ملفات المستند بعد التحويل.');document.save(source)
    original=hashlib.sha256(source.read_bytes()).hexdigest()
    started=time.perf_counter();_convert_with_word(source,destination)
    elapsed=time.perf_counter()-started
    with fitz.open(destination) as pdf:assert len(pdf)>0
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    renamed=source.with_name('renamed.docx');source.rename(renamed);renamed.rename(source)
    destination.unlink()
    immediate=word_processes()
    observed=[]
    for pid in set(immediate)-set(before):
        try:observed.append(psutil.Process(pid))
        except psutil.NoSuchProcess:pass
    _,alive=psutil.wait_procs(observed,timeout=5)
    assert not alive,'Observed Word processes remained after shutdown grace period'
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.windll.kernel32
    kernel.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,
        ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
    handle=kernel.CreateFileW(str(source),0x80000000,0,None,3,0x80,None)
    assert handle not in (None,ctypes.c_void_p(-1).value),'Original document still has incompatible open handles'
    kernel.CloseHandle(handle)
    print(json.dumps({'trial':trial,'conversion_seconds':elapsed,'word_pids_before':before,'word_pids_immediate':immediate,'word_pids_after_grace':word_processes(),'source_unchanged':True,'files_released':True}))
