from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from algorithm_service.paper_strategy import portfolio_quotes, PortfolioQuotesRequest


def test_batch_uses_actual_contracts_without_requesting_daily_history():
    seen = []
    def read(contract):
        seen.append(contract)
        if contract == 'RB2701':
            raise ValueError('warming')
        return {'contract': contract, 'marketState': 'LIVE', 'checkedAt': '2026-11-18T10:30:00+08:00',
                'quote': {'price': 900, 'dataTimestamp': '2026-11-18T10:30:00+08:00', 'dataStatus': 'FRESH',
                          'volumeMultiple': 20, 'priceTick': 1, 'marginPerLot': 2000, 'commissionPerLot': 6}}
    def forbidden(_):
        raise AssertionError('batch must not fetch daily history')
    result = portfolio_quotes(SimpleNamespace(execution_snapshot=read, snapshot=forbidden), ['FG701', 'RB2701', 'FG701'])
    assert seen == ['FG701', 'RB2701']
    assert result['quotes']['FG701']['signalBars'] == []
    assert result['quotes']['FG701']['spec']['volumeMultiple'] == 20
    assert list(result['errors']) == ['RB2701']


def test_root_symbols_and_changed_delivery_are_never_used_as_execution_quotes():
    with pytest.raises(HTTPException):
        portfolio_quotes(None, ['FG0'])
    feed = SimpleNamespace(execution_snapshot=lambda _: {'contract': 'FG705', 'marketState': 'LIVE',
        'checkedAt': '2026-11-18T10:30:00+08:00', 'quote': {'price': 900,
        'dataTimestamp': '2026-11-18T10:30:00+08:00', 'volumeMultiple': 20,
        'priceTick': 1, 'marginPerLot': 2000, 'commissionPerLot': 6}})
    result = portfolio_quotes(feed, ['FG701'])
    assert result['quotes'] == {}
    assert 'FG701' in result['errors']
    with pytest.raises(ValueError):
        PortfolioQuotesRequest(contracts=['FG701'] * 101)
