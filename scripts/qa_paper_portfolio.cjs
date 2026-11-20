/* Real Docker quotes and simulated fills, confined to a disposable QA tenant. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.test-tmp/paper-portfolio');fs.mkdirSync(out,{recursive:true});
const qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
const near=(a,b)=>assert.ok(Math.abs(a-b)<.011,`${a} != ${b}`);
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try {
  const base='http://localhost:8088',context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage();
  page.setDefaultTimeout(90000);const errors=[],orderTargets=[];
  page.on('pageerror',e=>errors.push(String(e)));
  page.on('request',r=>{if(r.method()==='POST'&&/\/sessions\/[^/]+\/orders$/.test(new URL(r.url()).pathname))orderTargets.push({path:new URL(r.url()).pathname,body:r.postDataJSON()})});
  const login=await context.request.post(base+'/api/v1/auth/login',{data:{identifier:qa.username,password:qa.password},headers:{Origin:base}});
  assert.equal(login.status(),200);const me=await(await context.request.get(base+'/api/v1/auth/me')).json();assert.equal(me.tenantId,qa.tenantId);
  const csrf=(await context.cookies(base)).find(c=>c.name==='aq_csrf').value,headers={Origin:base,'X-CSRF-Token':csrf};
  async function post(url,data){const r=await context.request.post(base+url,{headers,data,timeout:90000});assert.equal(r.status(),200,await r.text());return r.json()}
  const initial=await post('/api/v1/paper/sessions',{name:'Isolated multi-instrument QA',mode:'LIVE',symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'});
  const sessionPath=`/api/v1/paper/sessions/${initial.id}`;
  let account=await post(sessionPath+'/instruments/select',{symbol:initial.currentContract});
  assert.equal(account.multiInstrument,true);near(account.cashBalance,100000);assert.equal(account.positions.length,0);
  const fg=account.currentContract;
  await page.goto(base+'/paper?session='+initial.id);
  await page.getByLabel('添加或切换品种').waitFor();
  async function selected(action){const ready=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===sessionPath+'/instruments/select');await action();const r=await ready;assert.equal(r.status(),200,await r.text());const body=await r.json();assert.equal(body.id,initial.id);return body}
  async function choose(symbol){return selected(async()=>{await page.getByLabel('添加或切换品种').fill(symbol);await page.getByRole('button',{name:'添加 / 切换品种',exact:true}).click()})}
  async function submit(){const ready=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname===sessionPath+'/orders');await page.locator('.submit-order').click();const r=await ready;assert.equal(r.status(),200,await r.text());return r.json()}
  account=await choose('RB0');const rb=account.currentContract;assert.notEqual(fg,rb);near(account.cashBalance,100000);
  assert.equal(account.orderCount,0);assert.equal(orderTargets.length,0);
  account=await choose(fg);
  assert.equal(account.marketState,'LIVE','QA requires an open market and fresh real quotes');
  account=await submit();assert.equal(account.positions.length,1);assert.equal(account.positions[0].contract,fg);
  await choose(rb);
  await page.locator('.order-ticket .segmented').first().getByRole('button',{name:'卖出',exact:true}).click();
  const both=await submit();assert.equal(both.positions.length,2);assert.equal(both.fillCount,2);
  near(both.initialCash,100000);near(both.cashBalance,100000+both.realizedPnl-both.commissionPaid);
  near(both.totalMargin,both.positions.reduce((sum,p)=>sum+p.marginOccupied,0));
  near(both.equity,both.cashBalance+both.positions.reduce((sum,p)=>sum+p.unrealizedPnl,0));
  near(both.availableCash,both.equity-both.totalMargin-both.reservedCash);
  assert.equal(await page.getByLabel('全部品种持仓').locator('tbody tr').count(),2);
  await page.screenshot({path:path.join(out,'two-positions-desktop.png'),fullPage:true});
  await page.getByRole('button',{name:'记录心得',exact:true}).first().click();
  await page.getByLabel('我的心得与感悟').fill('多品种共用资金：分别观察信号，合并控制保证金，逐笔记录执行感受。');
  const saved=page.waitForResponse(r=>r.request().method()==='POST'&&/\/fills\/[^/]+\/note$/.test(new URL(r.url()).pathname));
  await page.getByRole('button',{name:'保存本笔心得',exact:true}).click();const savedResponse=await saved;assert.equal(savedResponse.status(),200);const notePath=new URL(savedResponse.url()).pathname;
  const targetBefore=orderTargets.length;
  const one=await selected(()=>page.getByLabel('全部品种持仓').locator('tbody tr').filter({hasText:fg}).getByRole('button',{name:'选择平仓',exact:true}).click());
  assert.equal(orderTargets.length,targetBefore,'Preparing a close must not submit an order');assert.equal(one.positions.length,2);
  await page.locator('.submit-order').filter({hasText:'提交卖出平仓'}).waitFor();
  const afterClose=await submit();assert.equal(afterClose.positions.length,1);assert.equal(afterClose.positions[0].contract,rb);
  await page.reload();await page.getByLabel('全部品种持仓').waitFor();assert.equal(await page.getByLabel('全部品种持仓').locator('tbody tr').count(),1);
  const note=await(await context.request.get(base+notePath)).json();assert.ok(note.content.includes('多品种共用资金'));
  await selected(()=>page.getByLabel('全部品种持仓').getByRole('button',{name:'选择平仓',exact:true}).click());
  await page.locator('.submit-order').filter({hasText:'提交买入平仓'}).waitFor();const flat=await submit();
  assert.equal(flat.positions.length,0);assert.equal(flat.fillCount,4);near(flat.cashBalance,100000+flat.realizedPnl-flat.commissionPaid);near(flat.equity,flat.cashBalance);
  assert.deepEqual(orderTargets.map(o=>o.body.contract),[fg,rb,fg,rb]);assert.ok(orderTargets.every(o=>o.path===sessionPath+'/orders'));
  const idempotent=await post(sessionPath+'/orders',orderTargets[0].body);assert.equal(idempotent.fillCount,4);near(idempotent.cashBalance,flat.cashBalance);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'portfolio-mobile.png'),fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',contracts:[fg,rb],fills:flat.fillCount,
   checks:['single-wallet','real-quotes-only','two-independent-positions','aggregate-margin-and-pnl','explicit-order-contract','switch-no-fill','independent-close','note-persistence','reload-persistence','idempotent-retry','mobile-no-overflow','no-page-errors']},null,2));
  console.log('PASS: two actual contracts share one wallet; independent closes, journals and reload persistence verified.');await context.close();
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
