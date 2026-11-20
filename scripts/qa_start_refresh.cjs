/* Fresh primary data only; all strategy runs belong to the disposable QA tenant. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const base='http://192.168.100.247:8088',context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage();page.setDefaultTimeout(90000);
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const login=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{identifier:qa.username,password:qa.password}});assert.equal(login.status(),200,await login.text());
 const me=await(await context.request.get(base+'/api/v1/auth/me')).json();assert.equal(me.tenantId,qa.tenantId);
 const csrf=(await context.cookies(base)).find(c=>c.name==='aq_csrf').value,headers={Origin:base,'X-CSRF-Token':csrf};
 async function post(url,data){const r=await context.request.post(base+url,{headers,data,timeout:90000});assert.equal(r.status(),200,await r.text());return r.json()}
 async function get(url){const r=await context.request.get(base+url);assert.equal(r.status(),200,await r.text());return r.json()}
 const account=await post('/api/v1/paper/sessions',{name:'Isolated fresh-start QA',mode:'LIVE',symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'});
 const prefix=`/api/v1/paper/sessions/${account.id}`,endpoint=prefix+'/automation';
 await post(prefix+'/instruments/select',{symbol:account.currentContract});await page.goto(base+'/paper?session='+account.id);await page.getByLabel('自动执行策略').waitFor();
 const out=path.join(root,'.test-tmp/start-refresh');fs.mkdirSync(out,{recursive:true});const receipts=[];
 for(let iteration=0;iteration<2;iteration++){
  const started=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===endpoint);
  await page.getByRole('button',{name:'启动所选合约策略',exact:true}).click();const response=await started;assert.equal(response.status(),200,await response.text());
  const state=await response.json(),run=state.runs.find(r=>r.enabled);assert.equal(run.contract,account.currentContract);assert.equal(run.status,'REFRESHING');
  let ready,last,start=Date.now();
  while(Date.now()-start<180000){
   last=(await get(endpoint)).runs.find(r=>r.id===run.id);
   if(last?.dataRefresh?.completedAt){ready=last;break}
   await new Promise(r=>setTimeout(r,1500));
  }
  assert.ok(ready,'Fresh download did not finish: '+JSON.stringify(last));const receipt=ready.dataRefresh;
  assert.equal(receipt.source,'TQSDK_FRESH_DOWNLOAD');assert.ok(receipt.dailyCount>0&&receipt.minuteCount>0);
  assert.equal(receipt.contract,account.currentContract);assert.ok(Date.parse(receipt.completedAt)>=Date.parse(receipt.requestedAt));
  assert.ok(Date.parse(receipt.latestMinuteTime)+60001>=Date.parse(receipt.sourceQuoteTime));
  receipts.push(receipt);
  await page.getByLabel(account.currentContract+' 数据更新回执').waitFor();
  if(iteration===0)await page.screenshot({path:path.join(out,'first-start-desktop.png'),fullPage:true});
  if(iteration===1){
   assert.notEqual(receipt.requestKey,receipts[0].requestKey);assert.ok(Date.parse(receipt.completedAt)>Date.parse(receipts[0].completedAt));
   await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'second-start-mobile.png'),fullPage:true});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
  }
  await post(endpoint+`/${run.id}/stop`);await page.reload();await page.getByLabel('自动执行策略').waitFor();
 }
 const final=await get(endpoint);assert.ok(final.runs.every(r=>!r.enabled));assert.equal(final.runs.filter(r=>r.dataRefresh?.completedAt).length,2);
 const wallet=await get(prefix);if(wallet.marketState==='CLOSED_CACHE'){assert.equal(wallet.orderCount,0);assert.equal(wallet.fillCount,0)}
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',origin:base,contract:account.currentContract,receipts,
  checks:['lan-login','start-waits-for-fresh-download','two-starts-two-primary-downloads','actual-contract-history','source-timestamps-not-restamped','receipt-persisted-after-reload','no-orders-while-market-closed','mobile-no-overflow','all-qa-runs-stopped']},null,2));
 console.log('PASS: each of two starts downloaded fresh primary daily/minute history; LAN login and persisted receipts verified.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
