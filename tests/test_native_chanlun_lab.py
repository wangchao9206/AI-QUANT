from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from algorithm_service.chanlun_lab import router
from backtesting.native_chanlun_lab import candidate_tape, execution_dataset, run_lab
from backtesting.chanlun_research import execute
from tests.test_chanlun_research import dataset, event


def test_first_observation_kept_after_later_invalidation_and_neutral_collision():
    record = {'type': 'BSP', 'id': 'a', 'eventType': 'OBSERVED', 'observedDate': '2020-01-03',
        'candidateObservedIndex': 2, 'endIndex': 1, 'signalType': 'B3', 'signalState': 'CANDIDATE',
        'direction': 'UP', 'invalidation': 90, 'eventSeq': 1}
    source = {'bars': [{'date': f'2020-01-0{i}'} for i in range(1, 5)],
              'events': [record, {**record, 'observedDate': '2020-01-04',
                                 'eventType': 'REVISED', 'signalState': 'INVALIDATED'}]}
    tape, accepted, conflicts, invalid = candidate_tape(source, 'THIRD')
    assert len(tape) == len(accepted) == 1 and not conflicts
    assert accepted[0]['confirmedIndex'] == 2 and invalid == {'a': 3}
    changed = deepcopy(source)
    changed['events'].insert(1, {**record, 'id': 'b', 'direction': 'DOWN', 'signalType': 'S3'})
    assert len(candidate_tape(changed, 'THIRD')[1]) == 0
    assert len(candidate_tape(changed, 'THIRD')[2]) == 2
    # A future revised state must not alter the earlier observation tape.
    assert candidate_tape({**source, 'events': source['events'][:1]}, 'THIRD')[0] == tape


def test_observed_invalidation_exits_next_open_and_does_not_look_forward():
    d = dataset([100] * 90)
    e = {**event(), 'structureId': 'a'}
    result = execute(d, [e], 1_000_000, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date(),
                     invalidation_observations={'a': 83})
    assert result['trades'][0]['entryIndex'] == 81
    assert result['trades'][0]['exitDate'] == d.bars[84].timestamp.date().isoformat()
    assert result['trades'][0]['exitReason'] == 'STRUCTURE_EXIT'
    early = execute(d, [e], 1_000_000, d.bars[80].timestamp.date(), d.bars[82].timestamp.date(),
                    invalidation_observations={'a': 83})
    assert early['trades'][0]['exitReason'] == 'WINDOW_END_LIQUIDATION'
    delayed = execute(d, [e], 1_000_000, d.bars[80].timestamp.date(), d.bars[-1].timestamp.date(),
                      delay=1, invalidation_observations={'a': 81})
    assert not delayed['trades'] and delayed['decisions'][0]['outcome'] == 'CANDIDATE_INVALID_WHILE_WAITING'


def test_frozen_delivery_cash_reconciles_all_five_variants_and_is_repeatable():
    r = run_lab('ALL')
    assert len(r['candidateTape']) == 18
    assert r['configHash'] == run_lab('ALL')['configHash']
    for v in r['variants']:
        m = v['metrics']
        assert m['netPnl'] == pytest.approx(sum(t['netPnl'] for t in v['trades']))
        assert m['finalEquity'] == pytest.approx(m['initialCash'] + m['netPnl'])
        assert m['fees'] > 0 and m['slippageCost'] > 0
        assert all(t['entryIndex'] > t['confirmedIndex'] for t in v['trades'])
    d = execution_dataset()
    for v in r['variants'][:3]:
        for t in v['trades']:
            assert t['contract'] == d.bars[t['entryIndex']].contract_symbol
    # Prices above a delivery contract's market range must never be used for fills.
    assert r['executable'] is False and len(r['assumptions']) >= 7


def test_private_endpoint_rejects_arbitrary_rules_and_cash_without_calculation():
    app = FastAPI(); app.include_router(router)
    client = TestClient(app)
    for body in ({'group': 'OPTIMIZE'}, {'initialCash': 123456}, {'code': 'anything'}, {'initialCash': '1000000'}):
        assert client.post('/internal/v1/chanlun/lab', json=body).status_code == 422
