/* Real LAN web app and real quotes, with an isolated temporary account; no orders. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const base='http://192.168.100.247:8088',context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage();page.setDefaultTimeout(60000);const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const login=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{identifier:qa.username,password:qa.password}});assert.equal(login.status(),200);
 const csrf=(await context.cookies(base)).find(c=>c.name==='aq_csrf').value;
 const created=await context.request.post(base+'/api/v1/paper/sessions',{headers:{Origin:base,'X-CSRF-Token':csrf},data:{name:'Isolated no-subplot QA',mode:'LIVE',symbol:'FG0',initialCash:100000,marginRate:.12,feeRate:.0001,slippageTicks:1,maxParticipationRate:.1,autoRoll:false,strategyId:'MANUAL'}});assert.equal(created.status(),200,await created.text());const account=await created.json();
 await page.goto(base+'/paper?session='+account.id);await page.getByRole('button',{name:'K线图',exact:true}).click();await page.locator('.candle-item').first().waitFor();
 const chart=page.locator('.tdx-trading-chart'),button=name=>chart.getByRole('button',{name,exact:true});
 async function hidden(){assert.equal(await button('无副图').getAttribute('aria-pressed'),'true');assert.equal(await chart.locator('.sub-chart-layer').count(),0);assert.equal(await chart.locator('.sub-hud-left').count(),0);assert.equal(await chart.locator('.ref-split').count(),0);assert.ok(Number(await chart.locator('clipPath rect').getAttribute('height'))>300);assert.ok(await chart.locator('.candle-item').count()>0)}
 await hidden();assert.equal(await chart.locator('[data-indicator="dkx"]').count(),1);
 const viewport=await chart.locator('.range-info').textContent();
 for(const type of ['MACD','VOL','涨跌柱']){
  await button(type).click();await chart.locator('.sub-chart-layer').waitFor();assert.equal(await button(type).getAttribute('aria-pressed'),'true');assert.ok(Number(await chart.locator('clipPath rect').getAttribute('height'))<200);
  await button('无副图').click();await hidden();assert.equal(await chart.locator('.range-info').textContent(),viewport);
 }
 for(const seconds of [300,900,86400,60]){
  const loaded=page.waitForResponse(r=>r.url().includes('/sessions/'+account.id+'/chart?')&&new URL(r.url()).searchParams.get('barSeconds')===String(seconds));
  await page.getByLabel('图表K线周期').selectOption(String(seconds));assert.equal((await loaded).status(),200);await chart.locator('.candle-item').first().waitFor();await hidden();
 }
 await page.getByRole('button',{name:'分时图',exact:true}).click();await page.locator('.intraday-chart').waitFor();await page.getByRole('button',{name:'K线图',exact:true}).click();await chart.locator('.candle-item').first().waitFor();await hidden();
 await page.getByLabel('显示 DKX 指标',{exact:true}).uncheck();for(const ma of [5,10,20,60,180])await chart.getByLabel('显示 MA'+ma+' 均线',{exact:true}).uncheck();
 assert.equal(await chart.locator('[data-indicator]').count(),0);assert.equal(await chart.locator('path[data-ma]').count(),0);
 const out=path.join(root,'.test-tmp/chart-no-subplot');fs.mkdirSync(out,{recursive:true});await page.locator('.paper-chart').screenshot({path:path.join(out,'candles-only-desktop.png')});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'candles-only-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);await hidden();
 const wallet=await(await context.request.get(base+'/api/v1/paper/sessions/'+account.id)).json();assert.equal(wallet.orderCount,0);assert.equal(wallet.fillCount,0);assert.deepEqual(errors,[]);
 assert.equal((await context.request.get(base+'/assets/TodayView-DjLrnBNR.js')).status(),200);
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',checks:['paper-default-no-subplot','MACD-VOL-change-restore','expanded-candle-area','viewport-preserved','period-switch-preserves-hidden-state','intraday-candle-switch-preserves-hidden-state','optional-pure-candles','mobile-no-overflow','no-orders','old-assets-preserved']},null,2));console.log('PASS: no-subplot default, restore buttons, expanded candles, switching, mobile and old assets; no orders.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
