/* Tests old clients, new clients and simulated missing chunks against the local Docker web app. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const {execFileSync}=require('node:child_process');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),out=path.join(root,'.test-tmp/frontend-asset-recovery');
const qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
// A fulfilled HTML fixture has no peer address in Chromium. Use localhost for
// interception scenarios; qa_lan_login.cjs separately checks the real LAN origin.
const base='http://localhost:8088',oldAsset='/assets/TodayView-DjLrnBNR.js';
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 async function loggedIn(){const c=await browser.newContext({viewport:{width:1440,height:1000}});const r=await c.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{identifier:qa.username,password:qa.password}});assert.equal(r.status(),200);return c}
 const old=await loggedIn(),oldPage=await old.newPage();oldPage.setDefaultTimeout(60000);
 const asset=await old.request.get(base+oldAsset);assert.equal(asset.status(),200);assert.match(asset.headers()['content-type'],/javascript/);assert.equal(asset.headers()['x-content-type-options'],'nosniff');assert.match(asset.headers()['cache-control'],/immutable/);
 const original=execFileSync('docker',['run','--pull=never','--rm','--network','none','--read-only','--entrypoint','cat','9210211ebf3e','/usr/share/nginx/html'+oldAsset]);
 assert.equal(crypto.createHash('sha256').update(await asset.body()).digest('hex'),crypto.createHash('sha256').update(original).digest('hex'));
 const unknown=await old.request.get(base+'/assets/qa-missing-release-file.js');assert.equal(unknown.status(),404);
 assert.match((await old.request.get(base+'/today')).headers()['cache-control'],/no-store/);
 const oldHtml=fs.readFileSync(path.join(out,'old-index.html'),'utf8');const oldErrors=[],oldFailures=[];
 oldPage.on('pageerror',e=>oldErrors.push(String(e)));oldPage.on('response',r=>{if(r.url().includes('/assets/')&&r.status()>=400)oldFailures.push(r.url())});
 await oldPage.route(base+'/today',async route=>{
  const response=await route.fetch(),headers={...response.headers()};delete headers['content-encoding'];delete headers['content-length'];
  await route.fulfill({status:200,headers,contentType:'text/html; charset=utf-8',body:oldHtml});
 });
 await oldPage.goto(base+'/today');await oldPage.locator('.today-desk').waitFor();await oldPage.getByRole('button',{name:'刷新待办',exact:true}).waitFor();
 assert.deepEqual(oldFailures,[]);assert.deepEqual(oldErrors,[]);await oldPage.screenshot({path:path.join(out,'old-client-today.png'),fullPage:true});await old.close();
 console.log('PASS: original missing asset byte-identical; old client and its original dependency graph load correctly.');

 const current=await loggedIn(),page=await current.newPage();page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await page.goto(base+'/today');await page.locator('.today-desk').waitFor();
 const csrf=(await current.cookies(base)).find(c=>c.name==='aq_csrf').value;
 const created=await current.request.post(base+'/api/v1/paper/sessions',{headers:{Origin:base,'X-CSRF-Token':csrf},data:{name:'Isolated asset recovery QA',mode:'LIVE',symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'}});assert.equal(created.status(),200,await created.text());const account=await created.json();
 await page.goto(base+'/paper?session='+account.id);await page.getByLabel('显示 DKX 指标',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('.intraday-chart [data-indicator="dkx"]')?.getAttribute('d')?.includes('L'));
 assert.deepEqual(errors,[]);await current.close();console.log('PASS: current Today, simulation and DKX load normally.');

 const recovering=await loggedIn(),recoveryPage=await recovering.newPage();recoveryPage.setDefaultTimeout(60000);let failed=0,documents=0;
 recoveryPage.on('request',r=>{if(r.isNavigationRequest()&&r.frame()===recoveryPage.mainFrame())documents++});
 await recovering.route(/\/assets\/TodayView-[^/]+\.js$/,async route=>{failed++;if(documents<=1)await route.fulfill({status:404,contentType:'application/javascript',body:'/* simulated removed release */'});else await route.continue()});
 await recoveryPage.goto(base+'/today?source=chunk-recovery#main-content');await recoveryPage.locator('.today-desk').waitFor();
 console.log('Recovery observations: '+JSON.stringify({documents,failed,marker:await recoveryPage.evaluate(()=>sessionStorage.getItem('aiquant:chunk-reload-at'))}));
 assert.equal(recoveryPage.url(),base+'/today?source=chunk-recovery#main-content');assert.equal(documents,2);assert.ok(failed>=2);assert.ok(await recoveryPage.evaluate(()=>sessionStorage.getItem('aiquant:chunk-reload-at')));await recovering.close();
 console.log('PASS: one missing module reloads once and preserves destination, query and anchor.');

 const broken=await loggedIn(),brokenPage=await broken.newPage();brokenPage.setDefaultTimeout(60000);let brokenDocuments=0,brokenAssets=0;
 brokenPage.on('request',r=>{if(r.isNavigationRequest()&&r.frame()===brokenPage.mainFrame())brokenDocuments++});
 await broken.route(/\/assets\/TodayView-[^/]+\.js$/,async route=>{brokenAssets++;await route.fulfill({status:404,contentType:'application/javascript',body:'/* persistent failure fixture */'})});
 await brokenPage.goto(base+'/today?source=persistent-fixture');await brokenPage.waitForFunction(()=>sessionStorage.getItem('aiquant:chunk-reload-at'));
 for(let i=0;i<30&&brokenAssets<2;i++)await brokenPage.waitForTimeout(200);
 assert.ok(brokenAssets>=2);await brokenPage.waitForTimeout(2000);assert.equal(brokenDocuments,2);await broken.close();
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',oldAsset,checks:['original-bytes-preserved','asset-mime-and-security-headers','missing-asset-remains-404','html-no-store','old-client-dependency-graph','new-today-and-paper-dkx','recovery-preserves-target-query-anchor','one-reload-only','persistent-failure-no-reload-loop']},null,2));
 console.log('PASS: persistent failure is bounded; no reload loop.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
