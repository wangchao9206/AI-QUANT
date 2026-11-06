import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from algorithm_service.monitor_api import ACTIVE_RULES, Parameters, Spec, router_for


def test_legacy_and_mixed_rules_are_rejected_but_opportunity_alerts_remain():
    for rules in (['BIG_BUY'], ['PRICE_UP_60S'], ['OUTCOME_PATTERN', 'BIG_BUY']):
        with pytest.raises(ValidationError, match='旧盘口定时扫描已下线'):
            Parameters(rules=rules)
    for rule in ACTIVE_RULES:
        assert Parameters(rules=[rule]).rules == [rule]
    spec = Spec(assetType='FUTURE', symbol='RB2701')
    assert spec.seconds == 900
    assert spec.parameters.rules == ['OUTCOME_PATTERN']


def test_catalog_and_validation_no_longer_offer_legacy_scans(monkeypatch):
    secret = 'isolated-test-internal-secret-32-characters'
    monkeypatch.setenv('IDENTITY_INTERNAL_SECRET', secret)
    app = FastAPI()
    app.include_router(router_for(object()))
    client = TestClient(app)
    headers = {'X-Identity-Service-Secret': secret}
    catalog = client.get('/internal/v1/monitor/catalog', headers=headers)
    assert catalog.status_code == 200
    assert {r['code'] for r in catalog.json()['rules']} == set(ACTIVE_RULES)
    response = client.post('/internal/v1/monitor/validate', headers=headers,
                           json={'assetType': 'FUTURE', 'symbol': 'RB2701',
                                 'parameters': {'rules': ['BIG_BUY']}})
    assert response.status_code == 422
