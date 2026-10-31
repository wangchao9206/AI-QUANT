import gzip
import hashlib
import json
import sqlite3
import zlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algorithm_service import research_library as library
from scripts.publish_research_library import ROOT, STUDIES, metadata, publish


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    target = tmp_path_factory.mktemp("research-publication")
    catalog = publish(output=target)
    return target, catalog


@pytest.fixture
def client(published, monkeypatch, tmp_path):
    target, _ = published
    monkeypatch.setattr(library, "PUBLISHED_ROOT", target)
    shadow = tmp_path / "shadow.json"
    shadow.write_bytes((ROOT / "docs/research/data/fu-regime-2026-10-27/shadow-state.json").read_bytes())
    monkeypatch.setattr(library, "OBSERVATION_PATH", shadow)
    app = FastAPI()
    app.include_router(library.router)
    return TestClient(app)


def test_all_scenarios_roundtrip_without_changing_frozen_sources(published):
    target, catalog = published
    assert catalog["totalRuns"] == 1570
    assert sum(s["count"] for s in STUDIES if s['id'] != 'fu-chanlun') == 1390
    for spec in STUDIES:
        folder = ROOT / "docs/research/data" / spec["folder"]
        rows = json.loads(gzip.decompress((folder / "full-ledgers.json.gz").read_bytes()))
        output = target / "generations" / catalog["revision"] / spec["id"]
        conn = sqlite3.connect(output / "runs.sqlite")
        actual = conn.execute("SELECT meta,metrics,payload FROM runs ORDER BY id").fetchall()
        conn.close()
        assert len(actual) == len(rows) == spec["count"]
        for original, (meta, metrics, payload) in zip(rows, actual):
            result = original.get("result", original)
            assert json.loads(meta) == metadata(spec["id"], original["key"])
            assert json.loads(metrics) == result["metrics"]
            assert json.loads(zlib.decompress(payload)) == {k: result.get(k, []) for k in ("curve", "trades", "decisions")}
        detail = json.loads((output / "study.json").read_text("utf-8"))
        assert detail["report"] == (ROOT / "docs/research" / spec["report"]).read_text("utf-8")
        for asset in detail["assets"]:
            assert hashlib.sha256((output / asset["name"]).read_bytes()).hexdigest() == asset["sha256"]
        for name in detail["reportLinks"].values():
            assert name == "@observation" or name in {a["name"] for a in detail["assets"]}
        for item in detail["comparisons"]:
            assert item["metrics"] == rows[item["id"] - 1]["result"]["metrics"]


def test_republish_reuses_immutable_generation(published):
    target, original = published
    db = target / "generations" / original["revision"] / "fu-regime/runs.sqlite"
    before = (db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest())
    assert publish(output=target) == original
    assert (db.stat().st_mtime_ns, hashlib.sha256(db.read_bytes()).hexdigest()) == before


def test_read_only_pagination_filters_and_ledger(client):
    base = "/api/v1/research/studies"
    catalog = client.get(base).json()
    for spec in STUDIES:
        url = base + "/" + spec["id"]
        detail = client.get(url).json()
        result = client.get(url + "/runs?page_size=3").json()
        assert result["total"] == spec["count"]
        assert len(result["items"]) == 3
        assert client.get(url + "/runs?page=2&page_size=3").json()["items"][0]["id"] == 4
        item = result["items"][0]
        found = client.get(url + "/runs", params={"family":item["family"], "capital":item["capital"], "cost":item["cost"], "stage":item["stage"]}).json()
        assert all(r["family"] == item["family"] and r["capital"] == item["capital"] for r in found["items"])
        ledger = client.get(url + "/runs/1").json()
        assert ledger["metrics"] == item["metrics"] and ledger["curve"]
        assert client.get(url + "/runs/99999").status_code == 404
        assert client.get(url + "/runs?family=' OR 1=1 --").json()["total"] == 0
        assert client.get(url + "/runs?page_size=101").status_code == 422
        assert client.get(url + "?revision=../../etc").status_code == 404
        assert client.post(url + "/runs").status_code == 405
        response = client.get(url + "/assets/all-runs.csv", params={"revision":catalog["revision"]})
        file = next(a for a in detail["assets"] if a["name"] == "all-runs.csv")
        assert hashlib.sha256(response.content).hexdigest() == file["sha256"]
        assert 'attachment' in response.headers["content-disposition"]
        assert client.get(url + "/assets/runs.sqlite").status_code == 404
        assert client.get(url + "/assets/study.json").status_code == 404
    assert client.get(base + "/unknown").status_code == 404


def test_observation_is_latest_saved_state_and_never_advances_it(client):
    path = library.OBSERVATION_PATH
    original = path.read_bytes()
    url = "/api/v1/research/studies/fu-regime/observation"
    response = client.get(url).json()
    assert response["state"]["asOf"] == json.loads(original)["asOf"]
    assert response["automaticUpdates"] is False and response["tradingEnabled"] is False
    assert path.read_bytes() == original
    state = json.loads(original)
    state["revision"] += 1
    path.write_text(json.dumps(state), "utf-8")
    assert client.get(url).json()["state"]["revision"] == state["revision"]
    assert client.get(url + "?download=true").json() == state
    state["config"]["initialCash"] += 1
    path.write_text(json.dumps(state), "utf-8")
    assert client.get(url).status_code == 503
    assert client.get("/api/v1/research/studies/daily-screen/observation").status_code == 404


def test_missing_publication_is_explicit_service_error(client, monkeypatch, tmp_path):
    monkeypatch.setattr(library, "PUBLISHED_ROOT", tmp_path / "unpublished")
    assert client.get("/api/v1/research/studies").status_code == 503


def test_chanlun_publication_retains_confirmation_clock_and_original_execution_prices(client):
    base = '/api/v1/research/studies/fu-chanlun'
    detail = client.get(base).json()
    assert detail['count'] == 180 and detail['observation'] is False
    assert len(detail['comparisons']) == 24
    assert {r['family'] for r in detail['comparisons']} == {
        'CHAN_SEGMENT_T3', 'CHAN_PEN_T3', 'RANGE_RETEST', 'CHANNEL_BREAKOUT'}
    assert '历史探索' in detail['report'] and '70' in detail['report']
    items = client.get(base + '/runs', params={'family': 'CHAN_PEN_T3', 'stage': 'VALIDATION',
        'capital': 1000000, 'cost': 1}).json()['items']
    selected = next(r for r in items if r['scale'] == 1 and r['mode'] == 'CAUSAL')
    ledger = client.get(base + '/runs/' + str(selected['id'])).json()
    assert ledger['trades']
    for t in ledger['trades']:
        assert t['pivotDate'] < t['confirmedDate'] < t['entryDate']
        assert t['contract'].startswith('FU') and t['contract'][2:].isdigit()
    assert sum(t['netPnl'] for t in ledger['trades']) == pytest.approx(ledger['metrics']['netPnl'])
    assert {'structure-audit.json', 'signal-example.png', 'verification.json'} <= {a['name'] for a in detail['assets']}
