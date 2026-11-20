/* Real Docker market data with a disposable QA ledger. Never submits an order. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.test-tmp/paper-live-chart');fs.mkdirSync(out,{recursive:true});
const qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{const base='http://localhost:8088',context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage();page.setDefaultTimeout(90000);
const errors=[],requests=[];page.on('pageerror',e=>errors.push(String(e)));page.on('request',r=>{if(r.url().includes('/api/v1/paper/'))requests.push({method:r.method(),path:new URL(r.url()).pathname})});
const login=await context.request.post(base+'/api/v1/auth/login',{data:{identifier:qa.username,password:qa.password},headers:{Origin:base}});assert.equal(login.status(),200);
const me=await(await context.request.get(base+'/api/v1/auth/me')).json();assert.equal(me.tenantId,qa.tenantId);
const csrf=(await context.cookies(base)).find(c=>c.name==='aq_csrf').value;
const created=await context.request.post(base+'/api/v1/paper/sessions',{headers:{Origin:base,'X-CSRF-Token':csrf},data:{name:'Isolated live chart QA',mode:'LIVE',symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'}});
assert.equal(created.status(),200,await created.text());const account=await created.json();
execFileSync('python',[path.join(__dirname,'manual_replay_qa_identity.py'),'age-live-valuation-fixture'],{stdio:'pipe'});
const sessionPath=`/api/v1/paper/sessions/${account.id}`;
const baseline=await(await context.request.get(base+sessionPath)).json();
function ready(seconds){return page.waitForResponse(async r=>{if(!r.url().includes(sessionPath+'/chart?'))return false;try{const d=await r.json();return d.barSeconds===seconds&&d.bars?.length>0&&(d.dataStatus==='FRESH'||d.marketState==='CLOSED_CACHE')}catch{return false}},{timeout:90000})}
const firstReady=ready(60);await page.goto(base+'/paper?session='+account.id);const first=await(await firstReady).json();
await page.locator('[aria-label="模拟分时图"] svg').waitFor();assert.equal(first.snapshotKind,'LIVE');
assert.ok(first.bars.every(b=>b.contract===account.currentContract));assert.ok(Date.parse(first.asOf)>Date.parse(baseline.currentMarketTime));
assert.ok(Date.parse(first.bars.at(-1).timestamp)>Date.parse(baseline.currentMarketTime));
assert.ok(!await page.getByText('历史日线背景',{exact:true}).count());assert.ok(!await page.getByText('本图为已完成日线',{exact:false}).count());
const next=await(await ready(60)).json();assert.ok(Date.parse(next.asOf)>Date.parse(first.asOf));
if(next.dataStatus==='FRESH')assert.ok(Date.now()-Date.parse(next.dataTimestamp)<65000);
await page.screenshot({path:path.join(out,'live-intraday-desktop.png'),fullPage:true});
await page.getByRole('button',{name:'K线图',exact:true}).click();await page.locator('.tdx-trading-chart').waitFor();
for(const seconds of [180,300,900,1800,3600,86400,60]){
 const response=ready(seconds);await page.getByLabel('图表K线周期').selectOption(String(seconds));const d=await(await response).json();
 assert.equal(d.snapshotKind,'LIVE');assert.ok(d.bars.every(b=>b.contract===account.currentContract));
 await page.locator('.tdx-trading-chart').waitFor();
}
await page.screenshot({path:path.join(out,'live-candle-desktop.png'),fullPage:true});
await page.getByRole('button',{name:'分时图',exact:true}).click();await page.locator('[aria-label="模拟分时图"] svg').waitFor();
await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'live-intraday-mobile.png'),fullPage:true});
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
const final=await(await context.request.get(base+sessionPath)).json();
for(const key of ['version','currentMarketTime','fillCount','orderCount','cashBalance'])assert.equal(final[key],baseline[key],key+' changed during read-only chart polling');
assert.ok(!requests.some(r=>r.method!=='GET'),'chart navigation sent a ledger mutation');assert.deepEqual(errors,[]);
fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',contract:account.currentContract,dataTimestamp:next.dataTimestamp,marketState:next.marketState,checks:['actual-live-source','not-clipped-to-old-valuation','forming-minute','automatic-read-only-refresh','all-seven-periods','actual-delivery-identity','no-orders-no-strategy','mobile-layout','no-page-errors']},null,2));
console.log('PASS: actual live intraday/candles, seven periods, automatic read-only refresh and unchanged ledger.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
