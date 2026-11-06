from copy import deepcopy
from datetime import datetime
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP
from unittest.mock import patch

import pytest
from backtesting.chan_signal import ChanTape, profile
from backtesting.workflow import compile_workflow
from chanlun_worker.data import load_dataset
from data.data_feed import KLineBar


def graph():
    return {'schemaVersion': 2, 'nodes': [
        {'id': 'market', 'type': 'MARKET'},
        {'id': 'chan', 'type': 'CHAN_SIGNAL', 'params': {**profile(), 'group': 'ALL'}},
        {'id': 'risk', 'type': 'RISK'},
        *[{'id': action.lower(), 'type': 'ACTION', 'params': {'action': action}} for action in ('BUY', 'SELL', 'FLATTEN')]],
        'edges': [{'id': 'market-chan', 'source': 'market', 'sourcePort': 'bars', 'target': 'chan', 'targetPort': 'market'},
                  *[{'id': 's-' + action, 'source': 'chan', 'sourcePort': port, 'target': action.lower(), 'targetPort': 'condition'} for action, port in [('BUY', 'buy'), ('SELL', 'sell'), ('FLATTEN', 'close')]],
                  *[{'id': 'r-' + action, 'source': 'risk', 'sourcePort': 'risk', 'target': action.lower(), 'targetPort': 'risk'} for action in ('BUY', 'SELL', 'FLATTEN')]]}


def bars():
    return [KLineBar(datetime.fromisoformat(b['timestamp']), b['open'], b['high'], b['low'], b['close'], b['volume'], 0, b['contract']) for b in load_dataset()]


def test_explicit_version_and_source_pins_cannot_be_bypassed():
    definition = graph()
    assert compile_workflow(definition).metadata()['engineVersion'] == 'workflow-daily-v2'
    for bad in ('schema', 'hash', 'missing', 'group', 'group_list'):
        altered = deepcopy(definition)
        if bad == 'schema': altered['schemaVersion'] = 1
        elif bad == 'hash': altered['nodes'][1]['params']['implementationHash'] = '0' * 64
        elif bad == 'missing': del altered['nodes'][1]['params']['rulesHash']
        elif bad == 'group': altered['nodes'][1]['params']['group'] = 'UNKNOWN'
        else: altered['nodes'][1]['params']['group'] = []
        with pytest.raises(ValueError): compile_workflow(altered)


def test_real_native_observations_are_prefix_causal_and_do_not_borrow_future():
    source = bars()[:650]
    program = compile_workflow(graph())
    full = program.prepare(source)
    prefix = program.prepare(source[:501])
    assert full.evaluate(500) == prefix.evaluate(500)
    changed = deepcopy(source)
    for bar in changed[501:]:
        bar.open *= 10; bar.high *= 10; bar.low *= 10; bar.close *= 10
    assert program.prepare(changed).evaluate(500) == full.evaluate(500)
    earlier = deepcopy(full.chan_tape.rows[500])
    full.evaluate(649)
    assert full.chan_tape.rows[500] == earlier
    shifted = program.prepare(source[1:501]).evaluate(499)
    old = next(n['value'] for n in prefix.evaluate(500).node_trace if n['type']=='CHAN_SIGNAL')
    new = next(n['value'] for n in shifted.node_trace if n['type']=='CHAN_SIGNAL')
    assert old['windowStart'] != new['windowStart'] and old['inputHash'] != new['inputHash']


def test_mutable_kernel_invalidation_keeps_the_earlier_candidate_and_explicit_exit_policy():
    class RevisingKernel:
        def __init__(self): self.zones = self; self.signals = []
        def push(self, bar):
            if bar['index'] == 50:
                self.signals.append({'signalType': 'B3', 'candidateObservedIndex': 50, 'endIndex': 45,
                                     'direction': 'UP', 'invalidation': 100, 'signalState': 'CANDIDATE'})
            if bar['index'] == 60:
                self.signals[0].update(signalState='INVALIDATED', invalidatedIndex=60)
    with patch('backtesting.chan_signal.NativeEngine', RevisingKernel):
        tape = ChanTape(bars()[:80])
    params = {**profile(), 'group': 'THIRD'}
    outputs, first = tape.observation(50, params, 0)
    assert outputs == {'buy': True, 'sell': False, 'close': False}
    assert first['candidates'][0]['signalState'] == 'CANDIDATE'
    assert first['candidates'][0]['eligibleAt'] is None
    assert tape.observation(51, params, 0)[0]['buy'] is False
    assert tape.observation(60, params, 1)[0]['close'] is True
    assert tape.observation(60, params, -1)[0]['close'] is False
    assert tape.observation(60, params, 1)[1]['exitRule'] == 'ANY_SAME_DIRECTION_INVALIDATED'
    first['candidates'][0]['signalState'] = 'CHANGED_BY_CALLER'
    assert tape.observation(50, params, 0)[1]['candidates'][0]['signalState'] == 'CANDIDATE'


def test_ledger_decimal_precision_and_utc_serialization_preserve_the_observation():
    source=bars()[:501]
    frozen=deepcopy(source)
    for bar in frozen:
        bar.timestamp=bar.timestamp.astimezone(timezone.utc)
        for field in ('open','high','low','close'):
            setattr(bar,field,float(Decimal(str(getattr(bar,field))).quantize(Decimal('0.000001'),rounding=ROUND_HALF_UP)))
    program=compile_workflow(graph())
    a,b=program.prepare(source).evaluate(500),program.prepare(frozen).evaluate(500)
    assert (a.signal,a.reason)==(b.signal,b.reason)
    assert next(n for n in a.node_trace if n['type']=='CHAN_SIGNAL')==next(n for n in b.node_trace if n['type']=='CHAN_SIGNAL')


def test_native_workflow_backtest_uses_real_delivery_prices_and_fixed_lots():
    from backtesting.native_chanlun_lab import execution_dataset
    from backtesting.independent_research import causal_prices
    from backtesting.backtester import QuantitativeBacktester
    from algorithm_service.models import BacktestRequest
    dataset=execution_dataset()
    definition=graph()
    request=BacktestRequest(symbol='FU0',strategy='WORKFLOW',workflowDefinition=definition,stopLossAtr=19,takeProfitAtr=49)
    assert request.stop_loss_atr==2 and request.take_profit_atr==3
    selected=dataset.bars[:300]
    result=QuantitativeBacktester(initial_capital=1000000).run_backtest(selected,
        signal_klines=causal_prices(dataset)[:300],strategy='WORKFLOW',symbol='FU0',workflow=definition,
        include_roll_cost=True,roll_events=[r for r in dataset.roll_events if r.execution_date<=selected[-1].timestamp.date()],
        contract_specs=dataset.contract_specs)
    entries=[t for t in result.trade_logs if t.action in ('OPEN_BUY','OPEN_SHORT')]
    assert entries and all(t.lots==1 for t in entries)
    assert entries[0].timestamp>selected[220].timestamp
