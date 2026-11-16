import gc
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from app.services import document_preview_service as service


@pytest.mark.parametrize('failure', [None, 'export', 'close', 'quit', 'wait'])
def test_word_cleanup_always_releases_apartment(monkeypatch,tmp_path,caplog,failure):
    events=[]
    def call(name):
        def invoke(*args,**kwargs):
            events.append(name)
            if failure==name:raise RuntimeError(name)
        return invoke
    doc=SimpleNamespace(ExportAsFixedFormat=call('export'),Close=call('close'))
    word=SimpleNamespace(Hwnd=123,Documents=SimpleNamespace(Open=lambda *a,**k:doc),Quit=call('quit'))
    client=SimpleNamespace(DispatchEx=lambda _:word)
    monkeypatch.setitem(sys.modules,'pythoncom',SimpleNamespace(CoInitialize=call('initialize'),CoUninitialize=call('uninitialize')))
    monkeypatch.setitem(sys.modules,'win32com',SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules,'win32com.client',client)
    monkeypatch.setitem(sys.modules,'win32process',SimpleNamespace(GetWindowThreadProcessId=lambda _: (1,99)))
    monkeypatch.setitem(sys.modules,'psutil',SimpleNamespace(Process=lambda _:SimpleNamespace(pid=99,wait=call('wait'))))
    monkeypatch.setattr(service,'_word_automation_lock',nullcontext)
    monkeypatch.setattr(service.sys,'platform','win32')
    source=tmp_path/'input.docx';source.write_bytes(b'original')
    if failure=='export':
        with pytest.raises(service.DocumentPreviewError):service._convert_with_word(source,tmp_path/'out.pdf')
    else:service._convert_with_word(source,tmp_path/'out.pdf')
    assert events==['initialize','export','close','quit','uninitialize','wait']
    assert source.read_bytes()==b'original'
    if failure in ('close','quit'):assert 'Failed to close Word' in caplog.text
    if failure=='wait':assert 'has not confirmed shutdown' in caplog.text


def test_failed_conversion_removes_only_current_temporary(monkeypatch,tmp_path):
    source=tmp_path/'original.docx';source.write_bytes(b'original')
    cache=tmp_path/'cache';cache.mkdir();unrelated=cache/'other.pdf';unrelated.write_bytes(b'keep')
    monkeypatch.setattr(service,'_preview_cache_dir',lambda:cache)
    def fail(source,destination):
        destination.write_bytes(b'partial')
        raise service.DocumentPreviewError('conversion failed')
    monkeypatch.setattr(service,'_convert_with_word',fail)
    monkeypatch.setattr(service,'_convert_with_libreoffice',fail)
    with pytest.raises(service.DocumentPreviewError):service.ensure_pdf_preview(source)
    assert list(cache.iterdir())==[unrelated]
    assert source.read_bytes()==b'original'


def test_libreoffice_timeout_cleans_current_directory(monkeypatch,tmp_path):
    monkeypatch.setattr(service.shutil,'which',lambda _: 'soffice')
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args[0],120)
    monkeypatch.setattr(service.subprocess,'run',timeout)
    with pytest.raises(service.DocumentPreviewError,match='timed out'):
        service._convert_with_libreoffice(tmp_path/'original.docx',tmp_path/'out.pdf')
    assert not list(tmp_path.glob('lo-*'))


def test_preview_lock_registry_does_not_retain_document_history():
    first=service._lock_for('same');assert service._lock_for('same') is first
    for index in range(1000):service._lock_for(str(index))
    gc.collect()
    assert len(service._LOCKS)<=1


def test_word_mutex_timeout_prevents_open(monkeypatch,tmp_path):
    from unittest.mock import Mock
    import ctypes
    kernel=SimpleNamespace(CreateMutexW=Mock(return_value=123),
        WaitForSingleObject=Mock(return_value=258),ReleaseMutex=Mock(),CloseHandle=Mock())
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(kernel32=kernel),raising=False)
    monkeypatch.setattr(service.sys,'platform','win32')
    with pytest.raises(service.DocumentPreviewError):
        with service._word_automation_lock():pytest.fail('must not enter')
    kernel.CloseHandle.assert_called_once_with(123)
    kernel.ReleaseMutex.assert_not_called()


def test_libreoffice_cleanup_failure_is_visible(monkeypatch,tmp_path,caplog):
    monkeypatch.setattr(service.shutil,'which',lambda _: 'soffice')
    monkeypatch.setattr(service.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=1))
    def fail(*args,**kwargs):raise PermissionError('locked temporary directory')
    monkeypatch.setattr(service.shutil,'rmtree',fail)
    with pytest.raises(service.DocumentPreviewError):
        service._convert_with_libreoffice(tmp_path/'original.docx',tmp_path/'out.pdf')
    assert 'Failed to remove conversion directory' in caplog.text
