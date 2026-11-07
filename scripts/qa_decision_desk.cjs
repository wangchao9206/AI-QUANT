/* Actual Vue UI, isolated synthetic API fixtures. Never connects to production APIs. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(__dirname,'../docs/implementation/decision-p0-2026-11-07');fs.mkdirSync(out,{recursive:true});
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.PROTOTYPE_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],checks=[];page.setDefaultTimeout(10000);page.on('pageerror',e=>errors.push(String(e)));
  const stamp='2026-11-06T07:00:00Z',id='10000000-0000-4000-8000-000000000001',planId='20000000-0000-4000-8000-000000000001';
  const fields={side:'LONG',entry:3120,stop:3098,target:3164,lots:1,equity:100000,budget:1000,hypothesis:'隔离验收假设，不是市场建议',invalidation:'隔离验收失效条件',validUntil:'2030-01-01T00:00:00Z'};
  const c={id,symbol:'RB2701',version:1,createdAt:stamp,updatedAt:stamp,origin:{id:42,monitorId:'fixture',rule:'LINES',label:'隔离验收事件 · 合成数据',symbol:'RB2701',assetType:'FUTURE',observedAt:stamp,createdAt:stamp,algorithmVersion:'fixture-v1',evidence:{triggerSeconds:900,featureAt:stamp,availableAt:stamp}},plans:[{id:planId,version:1,createdAt:stamp,fields}],reviews:[],paper:[]};
  c.origin.evidence.geometry={version:'fixture-v1',status:'READY',asOf:stamp,lines:[{id:'frozen',kind:'REGRESSION_CENTER',label:'隔离验收原线',startIndex:560,endIndex:599,startPrice:3100,endPrice:3120,startTimestamp:new Date(Date.parse(stamp)-59*900000).toISOString(),endTimestamp:stamp,knownAt:stamp}]};
  let stale=false;
  await page.route('**/api/**',async route=>{
   const req=route.request(),u=new URL(req.url());let body={};try{body=req.postDataJSON()||{}}catch{}
   let result={};
   if(u.pathname==='/api/v1/auth/me')result={id:'30000000-0000-4000-8000-000000000001',username:'isolated-qa',displayName:'隔离界面验收',email:null,tenantId:'40000000-0000-4000-8000-000000000001',role:'OWNER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:['paper.read','paper.write','market.read'],menus:[{id:'nav',parentId:null,label:'决策档案',path:'/paper/decisions',permission:'paper.read',sortOrder:1}]};
   else if(u.pathname.includes('/intraday'))result={symbol:'RB2701',seconds:900,period:'15m',source:'ISOLATED_FIXTURE',dataStatus:'CACHED',dataTimestamp:stamp,points:Array.from({length:100},(_,i)=>({timestamp:new Date(Date.parse(stamp)-(99-i)*900000).toISOString(),price:3100+i/5,open:3099+i/5,high:3102+i/5,low:3098+i/5,volume:1000+i,openInterest:10000}))};
   else if(u.pathname.endsWith('/instruments'))result={exchanges:[]};
   else if(u.pathname===`/api/v1/paper/decisions/${id}/plans`){c.version++;c.plans.unshift({id:`20000000-0000-4000-8000-${String(c.version).padStart(12,'0')}`,version:c.version,fields:body.fields,createdAt:stamp});result=c;}
   else if(u.pathname.endsWith('/check')){const f=c.plans[0].fields;result={planId:c.plans[0].id,version:c.version,checkedAt:stamp,ready:!stale&&f.budget>=500,reasons:stale?['隔离验收：当前报价过时']:f.budget<500?['隔离验收：风险超过预算']:[],scenarioLoss:500,marginRequired:10000,meaning:'仅隔离界面验收，不是生产核验',qualifiedForProfit:false};}
   else if(u.pathname.endsWith('/reviews')){c.reviews.unshift({id:'review-fixture',planId:c.plans[0].id,version:c.version,notes:body.notes,outcome:body.outcome,createdAt:stamp});result=c;}
   else if(u.pathname===`/api/v1/paper/decisions/${id}`)result=c;
   else if(u.pathname==='/api/v1/paper/decisions')result={items:[c],total:1,page:1,size:20};
   else return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'隔离验收未提供此接口'})});
   return route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
  });
  await page.goto((process.env.DECISION_UI_URL||'http://127.0.0.1:5179')+'/paper/decisions/'+id);
  await page.getByRole('heading',{name:'从原事件形成自己的计划'}).waitFor();
  await page.locator('.automatic-geometry').waitFor();assert.equal(await page.locator('.drawing-controls').count(),0);checks.push('原线按时间锚点重定位并只读绘制；没有手工编辑控件。');
  await page.getByRole('button',{name:'核验当前保存版本',exact:true}).click();
  await page.getByText('具备手动模拟账户准备条件',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'创建关联的手动模拟账户',exact:true}).isEnabled(),true);
  checks.push('服务端版本与原事件在同一页面展示；核验状态可见。');
  await page.getByLabel('单笔风险预算',{exact:true}).fill('100');
  assert.equal(await page.getByRole('button',{name:'创建关联的手动模拟账户',exact:true}).isDisabled(),true);
  await page.getByRole('button',{name:'保存新版本 v2',exact:true}).click();
  await page.getByText('新版本已保存到服务端；旧计划与复盘保留。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'核验当前保存版本',exact:true}).click();
  await page.getByText('隔离验收：风险超过预算',{exact:true}).waitFor();checks.push('修改清除就绪；保存新版本后超预算不可模拟。');
  await page.reload();await page.getByRole('heading',{name:'从原事件形成自己的计划'}).waitFor();
  assert.equal(await page.getByLabel('单笔风险预算',{exact:true}).inputValue(),'100');checks.push('刷新恢复API保存的版本，不依赖页面内存。');
  await page.getByLabel('依据与偏差',{exact:true}).fill('隔离验收：继续等待，不虚构成交。');await page.getByRole('button',{name:'保存私人复盘',exact:true}).click();await page.getByText('隔离验收：继续等待，不虚构成交。',{exact:true}).waitFor();checks.push('私人复盘回链对应计划版本。');
  stale=true;await page.getByRole('button',{name:'核验当前保存版本',exact:true}).click();await page.getByText('隔离验收：当前报价过时',{exact:true}).waitFor();checks.push('过时报价保留草稿并解释未就绪原因。');
  await page.evaluate(()=>{const banner=document.createElement('div');banner.textContent='隔离界面验收 · 合成行情与预警 · 不是生产数据';banner.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#3f235d;color:white;padding:8px;z-index:9999;font:12px sans-serif;text-align:center';document.body.append(banner)});
  const layouts=[];for(const width of [1440,390]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>scrollTo(0,0));const m=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth}));assert.ok(m.width<=m.viewport,JSON.stringify(m));layouts.push(m);await page.screenshot({path:path.join(out,`decision-desk-fixture-${width}.png`)});}
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(out,'ui-qa.json'),JSON.stringify({scope:'ACTUAL_VUE_UI_WITH_SYNTHETIC_INTERCEPTED_API_NOT_PRODUCTION_DATA',result:'PASSED',checks,layouts,browserErrors:errors},null,2)+'\n');
  console.log(JSON.stringify({result:'PASSED',checks:checks.length,layouts:layouts.length,errors:errors.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
