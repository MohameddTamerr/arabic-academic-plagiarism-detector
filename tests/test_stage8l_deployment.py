import pytest
from app.single_exe.app_controller import configured_worker_count


@pytest.mark.parametrize('value,expected',[(None,2),('1',1),('3',3)])
def test_explicit_executable_worker_profile(monkeypatch,value,expected):
    monkeypatch.delenv('SINGLE_EXE_WORKERS',raising=False)
    if value is not None:monkeypatch.setenv('SINGLE_EXE_WORKERS',value)
    assert configured_worker_count()==expected


@pytest.mark.parametrize('value',['0','-1','invalid'])
def test_invalid_worker_configuration_is_rejected(monkeypatch,value):
    monkeypatch.setenv('SINGLE_EXE_WORKERS',value)
    with pytest.raises(ValueError):configured_worker_count()
