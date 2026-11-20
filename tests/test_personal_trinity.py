from threading import BoundedSemaphore

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algorithm_service.personal_trinity import ARCHIVE_NAME, HISTORY, router_for


PATH = '/api/v1/research/personal-trinity/backtest'
CONFIGURATION = {
    'fastPeriod': 5, 'mediumPeriod': 10, 'slowPeriod': 20, 'convergenceDays': 3,
    'entryMinutes': 15, 'confirmation': 'either', 'addMode': 'MINUTE_ADD',
    'waitTradingDays': 10, 'symbol': 'FG701', 'costMultiplier': 2,
}


def client(capacity=None):
    app = FastAPI()
    app.include_router(router_for(capacity if capacity is not None else BoundedSemaphore(1)))
    return TestClient(app)


@pytest.mark.parametrize('overrides', [
    {'fastPeriod': 10}, {'convergenceDays': 1}, {'waitTradingDays': 0},
    {'entryMinutes': '15'}, {'entryMinutes': 15.0}, {'costMultiplier': True},
    {'confirmation': 'both'}, {'addMode': 'arbitrary'}, {'symbol': '..'}, {'history': 'arbitrary'},
])
def test_invalid_configuration_is_rejected_before_reading_history(overrides, tmp_path, monkeypatch):
    monkeypatch.setenv('HISTORY_CACHE_DIR', str(tmp_path))
    assert client().post(PATH, json={**CONFIGURATION, **overrides}).status_code == 422


def test_missing_archive_is_reported_and_capacity_is_released(tmp_path, monkeypatch):
    monkeypatch.setenv('HISTORY_CACHE_DIR', str(tmp_path))
    capacity = BoundedSemaphore(1)
    assert client(capacity).post(PATH, json=CONFIGURATION).status_code == 503
    assert capacity.acquire(blocking=False)
    assert client(capacity).post(PATH, json=CONFIGURATION).status_code == 429
    capacity.release()


def test_selected_parameters_drive_real_archive_replay(monkeypatch):
    if not (HISTORY / ARCHIVE_NAME).is_file():
        pytest.skip('local delivery-contract evidence archive not installed')
    monkeypatch.setenv('HISTORY_CACHE_DIR', str(HISTORY))
    replay = client()
    response = replay.post(PATH, json=CONFIGURATION)
    assert response.status_code == 200
    result = response.json()
    assert result['symbol'] == 'FG701'
    assert result['scope'] == {'first': '2026-09-10', 'last': '2026-11-16', 'scoreDays': 42}
    assert result['metrics']['netPnl'] == 288
    assert result['metrics']['primaryOpens'] == 2
    assert result['metrics']['addOpens'] == 1
    assert len(result['trades']) == 3

    revised = replay.post(PATH, json={**CONFIGURATION, 'addMode': 'NONE'}).json()
    assert revised['metrics']['netPnl'] == 592
    assert revised['metrics']['addOpens'] == 0
    assert revised['configuration']['addMode'] == 'NONE'
