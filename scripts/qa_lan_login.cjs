const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const base='http://192.168.100.247:8088',context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(45000);
 await page.goto(base+'/auth/login?next=/today');await page.getByLabel('账号或邮箱',{exact:true}).fill(qa.username);await page.getByLabel('密码',{exact:true}).fill(qa.password);
 const response=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/v1/auth/login'&&r.request().method()==='POST');
 await page.locator('button.submit').click();const login=await response;assert.equal(login.status(),200,await login.text());
 await page.waitForURL(base+'/today');const me=await context.request.get(base+'/api/v1/auth/me');assert.equal(me.status(),200);assert.equal((await me.json()).tenantId,qa.tenantId);
 assert.ok((await context.cookies(base)).some(c=>c.name==='aq_session'));
 const untrusted=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:'http://untrusted.invalid'},data:{identifier:qa.username,password:qa.password}});assert.equal(untrusted.status(),403);
 const local=await browser.newContext();const localLogin=await local.request.post('http://localhost:8088/api/v1/auth/login',{headers:{Origin:'http://localhost:8088'},data:{identifier:qa.username,password:qa.password}});assert.equal(localLogin.status(),200,await localLogin.text());await local.close();
 const out=path.join(root,'.test-tmp/lan-login');fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',origin:base,checks:['real-browser-login','redirect-today','session-cookie','authenticated-read','unknown-origin-rejected','localhost-login-preserved']},null,2));
 console.log('PASS: LAN browser login, cookie, authenticated request and localhost login; unknown origins still rejected.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
