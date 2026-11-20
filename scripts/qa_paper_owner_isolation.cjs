/* Real HTTP/browser checks. Both users and all mutations belong to one disposable QA tenant. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),read=name=>JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/'+name),'utf8'));
const owner=read('manual-replay-qa-identity.json'),peer=read('manual-replay-qa-peer.json');
assert.equal(owner.tenantId,peer.tenantId);assert.notEqual(owner.userId,peer.userId);
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const base='http://192.168.100.247:8088',context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.setDefaultTimeout(60000);
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));let headers;
 async function login(user){
  const r=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{identifier:user.username,password:user.password}});
  assert.equal(r.status(),200,await r.text());
  const me=await(await context.request.get(base+'/api/v1/auth/me')).json();assert.equal(me.tenantId,user.tenantId);assert.equal(me.id,user.userId);if(user===peer)assert.equal(me.role,'ADMIN');
  headers={Origin:base,'X-CSRF-Token':(await context.cookies(base)).find(c=>c.name==='aq_csrf').value};
 }
 async function call(method,url,data,status=200){const r=await context.request.fetch(base+url,{method,headers,data,timeout:90000});assert.equal(r.status(),status,method+' '+url+': '+await r.text());return status===204?null:r.json()}
 const denied=[];
 async function deny(method,url,data){const r=await context.request.fetch(base+url,{method,headers,data,timeout:90000});assert.ok([400,403,404,409].includes(r.status()),method+' '+url+': '+r.status()+' '+await r.text());denied.push({method,path:url,status:r.status()});}
 const request=(name,mode='LIVE')=>({name,mode,symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'});
 await login(owner);
 const a=await call('POST','/api/v1/paper/sessions',request('QA owner private wallet'));
 const prefix='/api/v1/paper/sessions/'+a.id;
 await call('POST',prefix+'/instruments/select',{symbol:a.currentContract});
 const auto=await call('POST',prefix+'/automation',{contract:a.currentContract,strategy:'MA20_MACD',lots:1,stopLossTicks:10,stopLossAtr:0,takeProfitAtr:0,intradayOnly:true});
 const run=auto.runs.find(r=>r.enabled);assert.ok(run);
 const catalog=await call('GET','/api/v1/paper/intraday/catalog');const instrument=catalog.symbols.find(s=>s.symbol==='FG701');assert.ok(instrument,'Real FG701 minute archive required');
 const historical=await call('POST','/api/v1/paper/sessions',{...request('QA private minute journal','HISTORICAL'),symbol:'FG701',startDate:instrument.startDate,endDate:instrument.startDate,barSeconds:60,stopLossTicks:0,intradayOnly:false});
 const hp='/api/v1/paper/sessions/'+historical.id;
 await call('POST',hp+'/orders',{clientOrderId:'qa-private-minute-open',side:'BUY',offset:'OPEN',orderType:'MARKET',quantity:1});
 const filled=await call('POST',hp+'/advance',{steps:1});assert.ok(filled.fills.length>0);const fill=filled.fills[0];
 const note='私有心得验收：只有创建人可以读取和修改本笔复盘';
 await call('POST',hp+'/fills/'+fill.id+'/note',{content:note,version:0});
 const versionsA=await call('GET','/api/v1/paper/personal/versions');assert.ok(versionsA.length>0);
 await call('POST','/api/v1/paper/personal/reflections',{category:'EMOTION',content:'QA owner private standalone reflection'},204);
 const before=await call('GET',prefix);
 await page.goto(base+'/paper?session='+a.id);await page.locator('.session-tabs').getByText(a.name,{exact:true}).waitFor();
 await page.getByRole('button',{name:'退出',exact:true}).click();await page.waitForURL(base+'/auth/login');
 await login(peer);
 assert.deepEqual(await call('GET','/api/v1/paper/sessions'),[]);
 const b=await call('POST','/api/v1/paper/sessions',{...request('QA peer private wallet'),ownerId:owner.userId});
 const visible=await call('GET','/api/v1/paper/sessions');assert.deepEqual(visible.map(s=>s.id),[b.id]);
 for(const p of [prefix,prefix+'/chart',prefix+'/records/fills',prefix+'/records/orders',prefix+'/automation',hp,hp+'/fills/'+fill.id+'/note'])await deny('GET',p);
 await deny('POST',prefix+'/orders',{clientOrderId:'qa-peer-forbidden-order',side:'BUY',offset:'OPEN',orderType:'MARKET',quantity:1,contract:a.currentContract});
 await deny('POST',prefix+'/instruments/select',{symbol:'FG701'});
 await deny('POST',prefix+'/advance',{steps:1});await deny('POST',prefix+'/pause');await deny('POST',prefix+'/resume');
 await deny('DELETE',prefix);
 await deny('POST',prefix+'/automation',{contract:a.currentContract,strategy:'MA20_MACD',lots:1,stopLossTicks:10,stopLossAtr:0,takeProfitAtr:0,intradayOnly:true});
 await deny('POST',prefix+'/automation/'+run.id+'/stop');
 await deny('POST',hp+'/fills/'+fill.id+'/note',{content:'forbidden overwrite',version:1});
 const versionsB=await call('GET','/api/v1/paper/personal/versions');assert.ok(versionsB.length>0);assert.ok(versionsB.every(b=>!versionsA.some(a=>a.id===b.id)));
 const reflections=await call('GET','/api/v1/paper/personal/reflections');assert.equal(reflections.total,0);
 await page.goto(base+'/paper?session='+a.id);await page.locator('.session-tabs').getByText(b.name,{exact:true}).waitFor();
 assert.equal(await page.getByText(a.name,{exact:true}).count(),0);assert.equal(await page.getByText(historical.name,{exact:true}).count(),0);
 const out=path.join(root,'.test-tmp/paper-owner-isolation');fs.mkdirSync(out,{recursive:true});await page.screenshot({path:path.join(out,'peer-cannot-see-owner.png'),fullPage:true});
 await call('POST','/api/v1/auth/logout',{});await login(owner);
 const after=await call('GET',prefix);for(const key of ['cashBalance','fillCount','orderCount'])assert.equal(before[key],after[key],key);
 assert.equal((await call('GET',hp+'/fills/'+fill.id+'/note')).content,note);
 assert.ok((await call('GET',prefix+'/automation')).runs.find(r=>r.id===run.id).enabled);
 await call('POST',prefix+'/automation/'+run.id+'/stop');
 assert.ok(!(await call('GET','/api/v1/paper/sessions')).some(s=>s.id===b.id));await deny('GET','/api/v1/paper/sessions/'+b.id);
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'browser-result.json'),JSON.stringify({status:'PASS',sameTenant:true,peerRole:'ADMIN',denied,
  checks:['separate-private-wallets','ownerId-body-cannot-assign-owner','same-browser-logout-login','direct-ID-read-and-mutation-denied','private-minute-fill-journal','private-default-strategy-versions','private-standalone-reflections','owner-wallet-and-notes-preserved','automation-stop-denied-for-peer','owner-cannot-see-peer','all-qa-runs-stopped']},null,2));
 console.log('PASS: same-tenant ADMIN cannot read or mutate another user’s wallets, notes or automation; same-browser switching verified.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
