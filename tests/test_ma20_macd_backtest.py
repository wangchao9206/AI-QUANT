from datetime import datetime
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from algorithm_service.ma20_macd_backtest import router_for


PATH = '/api/v1/research/ma20-macd/backtest'
ARCHIVE = Path(__file__).resolve().parents[1] / 'data' / 'history' / 'intraday-replay' / 'FG701.json'


def client(capacity=None):
    app = FastAPI()
    app.include_router(router_for(capacity if capacity is not None else BoundedSemaphore(1)))
    return TestClient(app)


def test_missing_archive_never_fabricates_trades(tmp_path, monkeypatch):
    monkeypatch.setenv('HISTORY_CACHE_DIR', str(tmp_path))
    capacity = BoundedSemaphore(1)
    replay = client(capacity)
    assert replay.post(PATH, json={'symbol': 'FG701'}).status_code == 503
    assert capacity.acquire(blocking=False)
    assert replay.post(PATH, json={'symbol': 'FG701'}).status_code == 429
    capacity.release()
    assert replay.post(PATH, json={'symbol': 'SC701'}).status_code == 422


def test_real_archive_trade_clocks_cost_and_cash_reconciliation(monkeypatch):
    if not ARCHIVE.is_file():
        pytest.skip('verified FG701 minutes and daily MACD are not installed')
    monkeypatch.setenv('HISTORY_CACHE_DIR', str(ARCHIVE.parent.parent))
    replay = client()
    response = replay.post(PATH, json={'symbol': 'FG701'})
    assert response.status_code == 200
    run = response.json()
    assert run['scope'] == {'first': '2026-10-19', 'last': '2026-11-16', 'scoreDays': 21}
    assert run['metrics']['closedTrades'] == len(run['trades']) == 71
    assert run['metrics']['netPnl'] == sum(t['netPnl'] for t in run['trades']) == -3932
    for trade in run['trades']:
        signal, entry, exit_at = (datetime.fromisoformat(trade[key]) for key in ('signalAt', 'entryAt', 'exitAt'))
        assert signal <= entry < exit_at
    stressed = replay.post(PATH, json={'symbol': 'FG701', 'costMultiplier': 2}).json()
    assert stressed['metrics']['fees'] == 2 * run['metrics']['fees']
    assert stressed['metrics']['netPnl'] < run['metrics']['netPnl']
    assert replay.post(PATH, json={'symbol': 'FG701', 'startDate': '2026-01-10'}).status_code == 422
