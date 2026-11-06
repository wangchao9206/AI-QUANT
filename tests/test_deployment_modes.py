"""Resolve Compose using template credentials, not the running environment."""
import json
import os
from pathlib import Path
import subprocess
import importlib.util
import pytest

ROOT=Path(__file__).resolve().parents[1]


def model(light):
    env=dict(os.environ,IDENTITY_INTERNAL_SECRET='isolated-compose-model-test-only-secret',COMPOSE_PROFILES='',TQSDK_USERNAME='',TQSDK_PASSWORD='',SMTP_PASSWORD='')
    args=['docker','compose','--env-file',str(ROOT/'infrastructure/.env.example'),'-f',str(ROOT/'infrastructure/docker-compose.yml')]
    if light:args+=['-f',str(ROOT/'infrastructure/docker-compose.light.yml')]
    return json.loads(subprocess.check_output(args+['config','--format','json'],env=env,text=True,encoding='utf-8'))


def test_all_java_runtimes_share_one_reactor_stage_and_expected_targets():
    services=model(False)['services']
    names=['identity-service','gateway-service','market-service','strategy-service','paper-trading-service','chanlun-service']
    for name in names:
        build=services[name]['build']
        assert build['dockerfile']=='Dockerfile' and build['target']==name
    source=(ROOT/'backend/Dockerfile').read_text(encoding='utf-8')
    assert source.count('mvn -B')==1
    for name in names:assert 'AS '+name in source


def test_light_mode_removes_only_unused_discovery_and_preserves_business_dependencies():
    full,light=model(False),model(True)
    assert 'nacos' not in light['services']
    for name,s in light['services'].items():
        if name!='nacos':assert 'nacos' not in s.get('depends_on',{})
    for name in ['identity-service','gateway-service','market-service','strategy-service','paper-trading-service','chanlun-service']:
        assert light['services'][name]['environment']['NACOS_ENABLED']=='false'
        assert light['services'][name]['environment']['ROCKETMQ_ENABLED']==full['services'][name]['environment']['ROCKETMQ_ENABLED']
    for name in ('postgres','redis','algorithm-service','rocketmq-broker','prometheus'):
        assert light['services'][name]['volumes']==full['services'][name]['volumes']
    assert light['services']['market-service']['depends_on']['rocketmq-topic-init']['condition']=='service_completed_successfully'
    assert full['services']['market-service']['depends_on']['nacos']['condition']=='service_healthy'


def test_compose_wrapper_passes_arguments_as_an_array_with_absolute_paths():
    spec=importlib.util.spec_from_file_location('compose_cli',ROOT/'scripts/compose.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    cmd=module.command('light',['up','-d','--no-build'])
    assert cmd[-3:]==['up','-d','--no-build']
    assert str(ROOT/'infrastructure/docker-compose.light.yml') in cmd


@pytest.mark.parametrize('setting',['NACOS_ENABLED=true','COMPOSE_PROFILES=discovery'])
def test_light_wrapper_refuses_existing_discovery_configuration(tmp_path,monkeypatch,setting):
    spec=importlib.util.spec_from_file_location('compose_cli',ROOT/'scripts/compose.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    (tmp_path/'infrastructure').mkdir()
    (tmp_path/'infrastructure/.env').write_text(setting,encoding='utf-8')
    monkeypatch.setattr(module,'ROOT',tmp_path)
    monkeypatch.setattr(module,'STATE',tmp_path/'absent.json')
    monkeypatch.setattr('sys.argv',['compose.py','--mode','light','up','-d'])
    monkeypatch.delenv('NACOS_ENABLED',raising=False)
    monkeypatch.delenv('COMPOSE_PROFILES',raising=False)
    with pytest.raises(SystemExit):module.main()
