/* Full deployed/dev application and its actual router. APIs are isolated synthetic fixtures. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'docs/implementation/decision-directory-fix-2026-11-07');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({executablePath:process.env.PROTOTYPE_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(10000);const errors=[],consoleErrors=[],checks=[],requests=[];page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error'&&/TypeError|Cannot read|Unhandled error/.test(m.text()))consoleErrors.push(m.text())});let mode='EMPTY';
 const stamp='2026-11-06T07:00:00Z',id='10000000-0000-4000-8000-000000000001';
 const c={id,symbol:'RB2701',version:0,origin:{id:42,label:'隔离目录验收记录',symbol:'RB2701',assetType:'FUTURE',observedAt:stamp,createdAt:stamp,algorithmVersion:'FIXTURE',evidence:{}},createdAt:stamp,updatedAt:stamp,plans:[],reviews:[],paper:[],sources:[]};
 await page.route('**/api/**',async route=>{const u=new URL(route.request().url());let result;
  if(u.pathname==='/api/v1/auth/me')result={id:'20000000-0000-4000-8000-000000000001',tenantId:'30000000-0000-4000-8000-000000000001',username:'isolated-directory-qa',email:null,role:'OWNER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:['paper.read','paper.write','market.read'],menus:[{id:'nav',parentId:null,label:'决策档案',path:'/paper/decisions',permission:'paper.read',sortOrder:1}]};
  else if(/^\/api\/v1\/paper\/decisions\/?$/.test(u.pathname)){
   requests.push(u.pathname+u.search);
   if(mode==='ERROR')return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'隔离用例：接口暂不可用'})});
   result=mode==='BAD_LIST'?{}:{items:mode==='DATA'?[c]:[],total:mode==='DATA'?1:0,page:1,size:20};
  }else if(u.pathname==='/api/v1/paper/decisions/'+id)result=mode==='BAD_DETAIL'?{items:[],total:0,page:1,size:20}:c;
  else if(u.pathname.endsWith('/instruments'))result={exchanges:[]};
  else return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'隔离验收未配置此接口'})});
  return route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
 });
 const base=process.env.DIRECTORY_UI_URL||'http://127.0.0.1:5179';
 const initialList=page.waitForResponse(r=>/^\/api\/v1\/paper\/decisions\/?$/.test(new URL(r.url()).pathname));await page.goto(base+'/paper/decisions');await initialList;
 if(process.argv.includes('--expect-bug')){
  await page.waitForFunction(()=>document.querySelector('.decision-desk')===null);await page.waitForTimeout(300);
  assert.ok(errors.length+consoleErrors.length>0);const report={scope:'DEPLOYED_FULL_APP_ROUTER_WITH_SYNTHETIC_API_READS',result:'BUG_REPRODUCED',errors,consoleErrors,requests};fs.writeFileSync(path.join(out,'before-fix.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));return;
 }
 for(const url of ['/paper/decisions','/paper/decisions/']){await page.goto(base+url);await page.getByRole('heading',{name:'我的决策档案',exact:true}).waitFor();await page.getByText('还没有决策档案。可从行情预警或研究工作台保存观察，也可预览导入自己的本机旧日志。',{exact:true}).waitFor();}
 assert.ok(requests.every(p=>p.startsWith('/api/v1/paper/decisions?')));checks.push('无ID和末尾斜杠两个目录URL都读取分页列表，空数据有可见说明。');
 mode='DATA';await page.reload();await page.locator('.case-row a').waitFor();await page.locator('.case-row a').click();await page.getByRole('heading',{name:'从原事件形成自己的计划',exact:true}).waitFor();await page.locator('.desk-heading').getByRole('link',{name:'我的档案',exact:true}).click();await page.locator('.case-row a').waitFor();checks.push('非空目录进入详情后能返回列表，不把列表响应当作详情。');
 mode='ERROR';await page.reload();await page.getByRole('alert').getByText('隔离用例：接口暂不可用',{exact:false}).waitFor();await page.getByRole('heading',{name:'我的决策档案',exact:true}).waitFor();mode='EMPTY';await page.getByRole('button',{name:'重新载入',exact:true}).click();await page.getByText('还没有决策档案。可从行情预警或研究工作台保存观察，也可预览导入自己的本机旧日志。',{exact:true}).waitFor();checks.push('接口失败显示错误和重试，恢复后显示空状态。');
 mode='BAD_DETAIL';await page.goto(base+'/paper/decisions/'+id);await page.getByRole('alert').getByText('档案详情数据结构异常',{exact:false}).waitFor();checks.push('详情误收列表结构时显示错误，不提交错误对象给模板。');
 mode='BAD_LIST';await page.goto(base+'/paper/decisions');await page.getByRole('alert').getByText('档案列表数据结构异常',{exact:false}).waitFor();checks.push('列表响应缺少items/total时显示错误，不崩溃。');
 mode='EMPTY';await page.reload();await page.getByRole('heading',{name:'我的决策档案',exact:true}).waitFor();const layouts=[];
 for(const width of [1440,390]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>{scrollTo(0,0);let b=document.getElementById('qa-mark');if(!b){b=document.createElement('div');b.id='qa-mark';b.textContent='隔离浏览器验收 · 合成API与身份 · 非生产用户数据';b.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#3f235d;color:white;padding:8px;text-align:center;font:12px sans-serif;z-index:9999';document.body.append(b)}});const m=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth}));assert.ok(m.width<=m.viewport);layouts.push(m);await page.screenshot({path:path.join(out,`directory-empty-fixture-${width}.png`)});}
 assert.deepEqual(errors,[]);assert.deepEqual(consoleErrors,[]);const result={scope:'FULL_APPLICATION_ROUTER_WITH_INTERCEPTED_SYNTHETIC_APIS_NOT_REAL_USER_DATA',url:base,result:'PASSED',checks,layouts,browserErrors:errors,consoleErrors};fs.writeFileSync(path.join(out,'browser-qa.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({result:'PASSED',checks:checks.length,widths:layouts.length,errors:errors.length}));
 }finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
