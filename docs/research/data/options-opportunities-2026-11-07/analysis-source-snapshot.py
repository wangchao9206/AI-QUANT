"""Snapshot screening, not an option historical backtest or trade execution."""
import hashlib,json,math,statistics,sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from algorithm_service.options import model_values
SOURCE=ROOT/'data/history/options-study-2026-11-07'
OUT=ROOT/'docs/research/data/options-opportunities-2026-11-07'
def stamp(t):return datetime.fromisoformat(t.replace('Z','+00:00')).timestamp()
def quality(r,u):
    if not all(r.get(k) for k in ('bidPrice','askPrice','bidVolume','askVolume','dataTimestamp')):return 'REJECT'
    if r['askPrice']<r['bidPrice'] or abs(stamp(r['dataTimestamp'])-stamp(u['dataTimestamp']))>60:return 'REJECT'
    if not r.get('risk',{}).get('iv'):return 'REJECT'
    spread=(r['askPrice']-r['bidPrice'])/((r['askPrice']+r['bidPrice'])/2)
    if spread<=.1 and (r.get('volume') or 0)>=500 and (r.get('openInterest') or 0)>=500:return 'CORE'
    if spread<=.15 and (r.get('volume') or 0)>=100 and (r.get('openInterest') or 0)>=200:return 'WATCH'
    return 'REJECT'
def compact(r):
    return {k:r.get(k) for k in ('symbol','optionClass','strike','bidPrice','askPrice','bidVolume','askVolume','volume','openInterest','volumeMultiple','priceTick','expiry','dataTimestamp','quality')}|{'iv':r['risk']['iv'],'delta':r['risk']['delta'],'theta':r['risk']['theta'],'vega':r['risk']['vega']}
def value(legs,spot,elapsed,vol_shift):
    total=0
    for r,side in legs:
        T=(stamp(r['expiry'])-stamp(r['dataTimestamp']))/(365*86400)-elapsed/365
        if T<=0:p=max(0,(spot-r['strike']) if r['optionClass']=='CALL' else (r['strike']-spot))
        else:p=model_values(spot,r['strike'],T,max(.0001,r['risk']['iv']+vol_shift),.02,0,r['optionClass'],'FUTURE')['price']
        total+=side*p*r['volumeMultiple']
    return total
def analyze():
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/'results.json').exists():raise SystemExit('Completed snapshot study exists; do not overwrite')
    inventory=json.loads((SOURCE/'collection.json').read_text(encoding='utf-8'));summaries=[];strategies=[];liquidity=[]
    protocol={'scope':'18 fixed domestic futures option roots; actual cached exchange quotes, never treated as executable live quotes. No option historical PnL/IV-rank/win-rate claims.',
       'core':'Valid two-sided non-crossed positive-size quote, <=60sec option-underlying skew, valid model IV, volume>=500 and OI>=500 and spread/mid<=10%.',
       'watch':'Same synchronization, volume>=100/OI>=200/spread<=15%; excluded from core trade shortlist.',
       'costs':'Buy at ask, sell at bid; additional1 tick per leg entry and1 tick per leg exit as explicit fee/slippage stress allowance, not broker actual fees.',
       'rv':'Sample standard deviation of last10/20/60 daily log returns, annualized sqrt252; only same actual contract; successor-confirmed completed daily bars. IV is ACT365 Black76, American approximation.',
       'scenarios':'After7 calendar days, underlying -10/-5/-2/0/+2/+5/+10%; IV -5/0/+5pp. European theoretical revaluation, not a realized or calibrated forecast.',
       'codeSha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for item in inventory:
        f=SOURCE/item['file'];assert hashlib.sha256(f.read_bytes()).hexdigest()==item['sha256']
        d=json.loads(f.read_text(encoding='utf-8'));u=d['underlying'];F=u['lastPrice'];root=item['root'];rows=d['contracts']
        for r in rows:r['quality']=quality(r,u)
        for r in rows:
            liquidity.append({'root':root,'symbol':r['symbol'],'quality':r['quality'],'volume':r.get('volume'),'oi':r.get('openInterest'),'quoteAt':r.get('dataTimestamp')})
        quoted=[r for r in rows if r.get('risk',{}).get('iv')]
        atm=sorted(quoted,key=lambda r:abs(r['strike']-F))[:2]
        history=ROOT/'data/history/intraday-active-study'/(root+'-15m.json');hist=json.loads(history.read_text(encoding='utf-8')) if history.exists() else None
        days=[];rv={};trend={};same=hist and hist['contract']==d['chain']['underlyingSymbol']
        if same:
            days=[b for b,n in zip(hist['barsDaily'],hist['barsDaily'][1:]) if stamp(n['timestamp'])<=stamp(u['dataTimestamp'])]
            for n in (10,20,60):
                prices=[b['price'] for b in days[-n-1:]]
                rv[str(n)]=statistics.stdev(math.log(b/a) for a,b in zip(prices,prices[1:]))*math.sqrt(252) if len(prices)==n+1 else None
            trend={'distanceMA20Pct':(F/statistics.mean(b['price'] for b in days[-20:])-1)*100,
                   'ma5vs20Pct':(statistics.mean(b['price'] for b in days[-5:])/statistics.mean(b['price'] for b in days[-20:])-1)*100,
                   'dailyThrough':days[-1]['timestamp']}
        summary={'root':root,'underlying':d['chain']['underlyingSymbol'],'spot':F,'quoteAt':u['dataTimestamp'],'expiry':d['chain']['expiry'],
             'daysAtQuote':(stamp(d['chain']['expiry'])-stamp(u['dataTimestamp']))/86400,'contracts':len(rows),
             'coreContracts':sum(r['quality']=='CORE' for r in rows),'watchContracts':sum(r['quality']=='WATCH' for r in rows),
             'atm':[{**compact(r),'spreadPct':(r['askPrice']-r['bidPrice'])/((r['askPrice']+r['bidPrice'])/2)*100 if r.get('askPrice') and r.get('bidPrice') else None} for r in atm],
             'atmIV':statistics.mean(r['risk']['iv'] for r in atm) if atm else None,'realizedVol':rv,'trend':trend,'sameContractHistory':bool(same),
             'historicalInputSha256':hashlib.sha256(history.read_bytes()).hexdigest() if same else None,'chainSha256':item['sha256']}
        summaries.append(summary)
        def add(kind,legs,max_loss,max_profit,breakevens):
            mult=legs[0][0]['volumeMultiple'];entry=sum(side*(r['askPrice'] if side>0 else r['bidPrice'])*r['volumeMultiple'] for r,side in legs)
            reserve=2*sum(r['priceTick']*r['volumeMultiple'] for r,side in legs)
            scenarios=[{'underlyingMovePct':move*100,'ivShiftPp':vol*100,'pnl':value(legs,F*(1+move),7,vol)-entry-reserve} for move in (-.1,-.05,-.02,0,.02,.05,.1) for vol in (-.05,0,.05)]
            strategies.append({'root':root,'type':kind,'legs':[{'side':'BUY' if side>0 else 'SELL',**compact(r)} for r,side in legs],
               'initialCashOutlay':entry,'costReserve':reserve,'maxLossBeforeCosts':max_loss,'maxProfitBeforeCosts':max_profit,
               'breakevens':breakevens,'expiryScenarios':[{'underlyingMovePct':m*100,'pnl':sum(side*max(0,F*(1+m)-r['strike'] if r['optionClass']=='CALL' else r['strike']-F*(1+m))*r['volumeMultiple'] for r,side in legs)-entry-reserve} for m in (-.1,-.05,-.02,0,.02,.05,.1)],
               'weekScenarios':scenarios,'minimumLegVolume':min(r['volume'] for r,side in legs),'minimumLegOI':min(r['openInterest'] for r,side in legs),
               'maxRelativeSpreadPct':max((r['askPrice']-r['bidPrice'])/((r['askPrice']+r['bidPrice'])/2)*100 for r,side in legs)})
        core=[r for r in rows if r['quality']=='CORE']
        # One nearest-ATM leg per direction: apply identical screen to every root.
        singles={}
        for kind in ('CALL','PUT'):
            choices=sorted([r for r in core if r['optionClass']==kind and .3<=abs(r['risk']['delta'])<=.7],key=lambda r:abs(r['strike']-F))
            if not choices:continue
            r=choices[0];singles[kind]=r;premium=r['askPrice']*r['volumeMultiple']
            add('LONG_'+kind,[(r,1)],premium,None,[r['strike']+(r['askPrice'] if kind=='CALL' else -r['askPrice'])])
            add('NAKED_SHORT_'+kind,[(r,-1)],None,r['bidPrice']*r['volumeMultiple'],[r['strike']+(r['bidPrice'] if kind=='CALL' else -r['bidPrice'])])
        if len(singles)==2 and singles['CALL']['strike']==singles['PUT']['strike']:
            c,p=singles['CALL'],singles['PUT'];debit=c['askPrice']+p['askPrice'];credit=c['bidPrice']+p['bidPrice'];K=c['strike'];mult=c['volumeMultiple']
            add('LONG_STRADDLE',[(c,1),(p,1)],debit*mult,None,[K-debit,K+debit])
            add('SHORT_STRADDLE',[(c,-1),(p,-1)],None,credit*mult,[K-credit,K+credit])
        for kind in ('CALL','PUT'):
            options=sorted([r for r in core if r['optionClass']==kind],key=lambda r:r['strike']);pairs=[]
            for a,b in zip(options,options[1:]):
                width=b['strike']-a['strike']
                long=b if kind=='PUT' else a;short=a if kind=='PUT' else b
                if not .25<=abs(long['risk']['delta'])<=.7 or not .005<=width/F<=.06:continue
                debit=long['askPrice']-short['bidPrice'];mult=a['volumeMultiple']
                if not 0<debit<width or mult!=b['volumeMultiple']:continue
                pairs.append((abs(long['strike']-F),long,short,debit,width,mult))
            for _,long,short,debit,width,mult in sorted(pairs,key=lambda p:p[0])[:2]:
                add('BEAR_PUT_DEBIT' if kind=='PUT' else 'BULL_CALL_DEBIT',[(long,1),(short,-1)],debit*mult,(width-debit)*mult,[long['strike']-debit if kind=='PUT' else long['strike']+debit])
                credit=long['bidPrice']-short['askPrice']
                if 0<credit<width:
                    add('BULL_PUT_CREDIT' if kind=='PUT' else 'BEAR_CALL_CREDIT',[(long,-1),(short,1)],(width-credit)*mult,credit*mult,[long['strike']-credit if kind=='PUT' else long['strike']+credit])
    result={'scope':'Snapshot structural candidates; no claim of demonstrated positive expected returns','chains':len(summaries),'contracts':sum(s['contracts'] for s in summaries),
            'coreContracts':sum(s['coreContracts'] for s in summaries),'watchContracts':sum(s['watchContracts'] for s in summaries),
            'summaries':summaries,'strategies':strategies,'strategyCount':len(strategies)}
    (OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    (OUT/'liquidity-ledger.json').write_text(json.dumps(liquidity,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'chains':result['chains'],'contracts':result['contracts'],'core':result['coreContracts'],'watch':result['watchContracts'],'strategies':len(strategies)},ensure_ascii=True))
if __name__=='__main__':analyze()
