from dataclasses import asdict
import json
import pytest
from fastlanelabs_sdk import registry, azure_blob


def test_remote_catalog_is_cached_and_survives_an_outage(tmp_path, monkeypatch):
    monkeypatch.delenv('FASTLANELABS_REGISTRY_REMOTE', raising=False)
    entries = registry.load()
    data = {'apps': {k: {key:value for key,value in asdict(v).items() if key != 'id'} for k,v in entries.items()}}
    cache = tmp_path/'catalog.json'
    monkeypatch.setenv('FASTLANELABS_REGISTRY_REMOTE', 'true')
    monkeypatch.setenv('FASTLANELABS_REGISTRY_CACHE', str(cache))
    monkeypatch.setattr(registry, '_cached_catalog', None)
    monkeypatch.setattr(registry, '_catalog_expires', 0)
    monkeypatch.setattr(azure_blob, 'get_json', lambda *args: data)
    assert registry.load()['fastai'].app_id == 'chat'
    assert json.loads(cache.read_text()) == data
    monkeypatch.setattr(registry, '_cached_catalog', None)
    monkeypatch.setattr(registry, '_catalog_expires', 0)
    monkeypatch.setattr(azure_blob, 'get_json', lambda *args: (_ for _ in ()).throw(RuntimeError('offline')))
    assert registry.load()['fastai'].app_id == 'chat'


@pytest.mark.parametrize('fields', [
    {'backend_package':'../../escape','repo':''},
    {'backend_package':'fastlanelabs_app_test','repo':'','min_role':'unknown'},
    {'backend_package':'fastlanelabs_app_test','repo':'','app_id':'../escape'},
])
def test_bad_catalog_metadata_is_rejected(fields):
    with pytest.raises(ValueError):
        registry._entries({'apps':{'test':fields}})
