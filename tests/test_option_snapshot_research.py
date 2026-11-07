from scripts.analyze_option_opportunities import quality,value

def row(**updates):
    return {'bidPrice':10,'askPrice':10.5,'bidVolume':2,'askVolume':2,'dataTimestamp':'2026-11-06T14:59:00+00:00',
            'volume':1000,'openInterest':1000,'risk':{'iv':.2},**updates}

def test_liquidity_screen_rejects_crossed_empty_and_unsynchronized_quotes():
    underlying={'dataTimestamp':'2026-11-06T14:59:00+00:00'}
    assert quality(row(),underlying)=='CORE'
    for change in ({'bidPrice':11},{'askVolume':0},{'dataTimestamp':'2026-11-06T14:57:59+00:00'}):
        assert quality(row(**change),underlying)=='REJECT'
    assert quality(row(volume=200),underlying)=='WATCH'

def leg(strike,kind):
    return {'strike':strike,'optionClass':kind,'volumeMultiple':10,'dataTimestamp':'2026-11-06T00:00:00+00:00',
            'expiry':'2026-11-13T00:00:00+00:00','risk':{'iv':.2}}

def test_expired_vertical_payoff_and_short_reverse_are_bounded():
    spread=[(leg(100,'CALL'),1),(leg(110,'CALL'),-1)]
    for spot,expected in ((90,0),(105,50),(120,100)):
        assert value(spread,spot,8,0)==expected
        assert value([(r,-side) for r,side in spread],spot,8,0)==-expected

def test_long_volatility_sensitivity_and_very_short_time_are_finite():
    call=[(leg(100,'CALL'),1)]
    assert value(call,100,0,.05)>value(call,100,0,0)>value(call,100,0,-.05)
    assert value(call,100,8,0)==0
