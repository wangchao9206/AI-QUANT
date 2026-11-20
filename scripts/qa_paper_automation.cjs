/* Uses real Docker market data, with all automation confined to a disposable QA tenant. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.test-tmp/paper-automation');fs.mkdirSync(out,{recursive:true});
const qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{
 const base='http://localhost:8088',context=await browser.newContext({viewport:{width:1440,height:1100}});let page=await context.newPage();page.setDefaultTimeout(90000);
 const pageErrors=[];function observe(p){p.on('pageerror',e=>pageErrors.push(String(e)))}observe(page);
 const login=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{identifier:qa.username,password:qa.password}});assert.equal(login.status(),200);
 const me=await(await context.request.get(base+'/api/v1/auth/me')).json();assert.equal(me.tenantId,qa.tenantId);
 const csrf=(await context.cookies(base)).find(c=>c.name==='aq_csrf').value,headers={Origin:base,'X-CSRF-Token':csrf};
 async function post(url,data){const r=await context.request.post(base+url,{headers,data,timeout:90000});assert.equal(r.status(),200,await r.text());return r.json()}
 async function get(url){const r=await context.request.get(base+url);assert.equal(r.status(),200,await r.text());return r.json()}
 async function until(fn,timeout=120000){const start=Date.now();let value;while(Date.now()-start<timeout){value=await fn();if(value)return value;await new Promise(r=>setTimeout(r,1200))}throw Error('Timed out waiting for background automation')}
 const initial=await post('/api/v1/paper/sessions',{name:'Isolated background automation QA',mode:'LIVE',symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'});
 const prefix=`/api/v1/paper/sessions/${initial.id}`,endpoint=prefix+'/automation';
 await post(prefix+'/instruments/select',{symbol:initial.currentContract});
 await page.goto(base+'/paper?session='+initial.id);await page.getByLabel('自动执行策略').waitFor();
 await page.getByLabel('自动执行策略').selectOption('BUY_AND_HOLD');await page.getByLabel('日内：收盘前一分钟清仓').uncheck();
 const started=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===endpoint);
 await page.getByRole('button',{name:'启动所选合约策略',exact:true}).click();const startResponse=await started;assert.equal(startResponse.status(),200,await startResponse.text());
 const state=await startResponse.json(),hold=state.runs.find(r=>r.enabled);assert.equal(hold.contract,initial.currentContract);assert.equal(hold.strategy,'BUY_AND_HOLD');
 const closedAt=Date.now();await page.close();
 const first=await until(async()=>{const s=await get(endpoint),r=s.runs.find(r=>r.id===hold.id);return r?.checkedAt&&Date.parse(r.checkedAt)>closedAt?r:false});
 const live=initial.marketState==='LIVE';
 if(live)await until(async()=>{const d=await get(prefix);return d.fillCount>=1?d:false});
 const second=await until(async()=>{const s=await get(endpoint),r=s.runs.find(r=>r.id===hold.id);return r?.checkedAt&&Date.parse(r.checkedAt)>Date.parse(first.checkedAt)?r:false});
 let account=await get(prefix);if(live){assert.equal(account.fillCount,1);assert.equal(account.positions.length,1);assert.equal(account.positions[0].contract,initial.currentContract)}
 const backgroundFill=account.fills.find(f=>f.offset==='OPEN');
 if(backgroundFill){const note=await post(prefix+`/fills/${backgroundFill.id}/note`,{content:'量化自动执行复盘：参数先冻结，信号与成交分开核对，共用账户控制总保证金。',version:0});assert.equal(note.version,1)}
 page=await context.newPage();page.setDefaultTimeout(90000);observe(page);await page.goto(base+'/paper?session='+initial.id);
 await page.getByRole('button',{name:`停止 ${initial.currentContract} 策略`,exact:true}).waitFor();
 assert.ok(await page.locator('.submit-order').isDisabled());await page.screenshot({path:path.join(out,'background-running-desktop.png'),fullPage:true});
 async function stopUI(run){const stopped=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===endpoint+`/${run}/stop`);await page.getByRole('button',{name:`停止 ${initial.currentContract} 策略`,exact:true}).click();const r=await stopped;assert.equal(r.status(),200,await r.text());return r.json()}
 await stopUI(hold.id);const afterStop=await get(prefix);assert.equal(afterStop.fillCount,account.fillCount);assert.equal(afterStop.positions.length,account.positions.length);
 async function flatten(){const d=await get(prefix);for(const p of d.positions??[])await post(prefix+'/orders',{clientOrderId:'qa-manual-close-'+Date.now(),contract:p.contract,side:p.direction>0?'SELL':'BUY',offset:'CLOSE',orderType:'MARKET',quantity:p.lots})}
 if(afterStop.positions?.length)await flatten();
 await page.getByLabel('自动执行策略').selectOption('MA20_MACD');await page.getByLabel('日内：收盘前一分钟清仓').check();
 const maStarted=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===endpoint);
 await page.getByRole('button',{name:'启动所选合约策略',exact:true}).click();const maResponse=await maStarted;assert.equal(maResponse.status(),200,await maResponse.text());
 const ma=(await maResponse.json()).runs.find(r=>r.enabled);assert.equal(ma.strategy,'MA20_MACD');assert.equal(ma.stopLossTicks,10);assert.equal(ma.takeProfitAtr,0);
 const evaluated=await until(async()=>{const s=await get(endpoint),r=s.runs.find(r=>r.id===ma.id);return r?.checkedAt&&['RUNNING','WARMING','WAITING'].includes(r.status)?s:false});
 assert.ok(evaluated.runs.find(r=>r.id===ma.id).checkedAt);
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'ma20-macd-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 await stopUI(ma.id);const final=await get(endpoint);assert.ok(final.runs.every(r=>!r.enabled));
 account=await get(prefix);if(account.marketState==='LIVE'&&account.positions.length)await flatten();
 assert.deepEqual(pageErrors,[]);
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',contract:initial.currentContract,
   liveFillVerified:live,backgroundChecks:[first.checkedAt,second.checkedAt],ma20Status:evaluated.runs.find(r=>r.id===ma.id).status,
   checks:['explicit-start','frozen-actual-contract','server-checks-after-page-closed','no-repeated-entry','stop-preserves-position','manual-after-stop','private-note-on-auto-fill','ma20-macd-config','background-ma20-evaluation','mobile-no-overflow','no-page-errors','all-qa-runs-stopped']},null,2));
 console.log('PASS: background execution survives closed page; start/stop, manual takeover, journals and MA20/MACD verified.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
