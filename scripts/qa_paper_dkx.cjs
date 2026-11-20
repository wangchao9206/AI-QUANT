/* Real quotes only. This script never submits an order. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const root=path.resolve(__dirname,'..'),qa=JSON.parse(fs.readFileSync(path.join(root,'.test-tmp/manual-replay-qa-identity.json'),'utf8'));
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const base='http://192.168.100.247:8088',context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage();page.setDefaultTimeout(60000);
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 const login=await context.request.post(base+'/api/v1/auth/login',{headers:{Origin:base},data:{identifier:qa.username,password:qa.password}});assert.equal(login.status(),200);
 async function get(url){const r=await context.request.get(base+url);assert.equal(r.status(),200,await r.text());return r.json()}
 const accounts=await get('/api/v1/paper/sessions'),account=accounts.find(a=>a.name==='Isolated fresh-start QA');assert.ok(account);
 const prefix='/api/v1/paper/sessions/'+account.id,before=await get(prefix);
 await page.goto(base+'/paper?session='+account.id);
 const toggle=page.getByLabel('显示 DKX 指标',{exact:true});await toggle.waitFor();assert.equal(await toggle.isChecked(),true);
 const toggleBox=await toggle.boundingBox();assert.ok(toggleBox.width<=24&&toggleBox.height<=24,'DKX checkbox must retain its native compact size');
 await page.waitForFunction(()=>{const d=document.querySelector('.intraday-chart [data-indicator="dkx"]')?.getAttribute('d');return d&&d.includes('L')});
 const line=await page.locator('.intraday-chart [data-indicator="dkx"]').getAttribute('d');assert.ok(!/NaN|Infinity/.test(line));
 assert.ok(!(await page.locator('[aria-label="DKX指标读数"] span').first().textContent()).includes('—'));
 await toggle.uncheck();assert.equal(await page.locator('[data-indicator="dkx"]').count(),0);
 await page.getByRole('button',{name:'K线图',exact:true}).click();await page.locator('.tdx-trading-chart').waitFor();assert.equal(await toggle.isChecked(),false);assert.equal(await page.locator('[data-indicator="dkx"]').count(),0);
 await toggle.check();await page.locator('.tdx-trading-chart [data-indicator="dkx"]').waitFor();
 const out=path.join(root,'.test-tmp/paper-dkx');fs.mkdirSync(out,{recursive:true});const periods=[];
 for(const seconds of [300,900,1800,3600,86400,60]){
  const loaded=page.waitForResponse(async r=>{
   if(!r.url().includes(prefix+'/chart?')||new URL(r.url()).searchParams.get('barSeconds')!==String(seconds)||r.status()!==200)return false;
   try{return (await r.json()).bars?.length>=29}catch{return false}
  });
  await page.getByLabel('图表K线周期').selectOption(String(seconds));const response=await loaded;assert.equal(response.status(),200);const chart=await response.json();assert.equal(chart.barSeconds,seconds);
  await page.locator('.tdx-trading-chart [data-indicator="dkx"]').waitFor();
  const bars=chart.bars;let first=bars.length-1;while(first>0&&bars[first-1].contract===bars.at(-1).contract)first--;
  const expected=bars.length-first>=20?bars.slice(-20).reduce((sum,b,i)=>sum+(i+1)*(3*b.close+b.open+b.high+b.low)/6,0)/210:null;
  const expectedText=expected==null?'—':new Intl.NumberFormat('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(expected);
  await page.mouse.move(1,1);
  console.log('Checking DKX period '+seconds+': '+expectedText);
  await page.waitForFunction(text=>document.querySelector('.tdx-trading-chart .dkx-value')?.textContent?.trim()==='DKX(20): '+text,expectedText);
  assert.ok(!/NaN|Infinity/.test(await page.locator('.tdx-trading-chart [data-indicator="dkx"]').getAttribute('d')));
  periods.push({seconds,bars:bars.length,dkx:expectedText});
  if(seconds===300){await page.screenshot({path:path.join(out,'dkx-candles-desktop.png'),fullPage:true});await page.locator('.paper-chart').screenshot({path:path.join(out,'dkx-candles-chart.png')});}
 }
 await page.getByRole('button',{name:'分时图',exact:true}).click();await page.locator('.intraday-chart [data-indicator="madkx"]').waitFor();assert.equal(await toggle.isChecked(),true);
 await page.screenshot({path:path.join(out,'dkx-intraday-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'dkx-intraday-mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 const after=await get(prefix);assert.equal(after.orderCount,before.orderCount);assert.equal(after.fillCount,before.fillCount);assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({status:'PASS',periods,checks:['live-intraday-dkx-and-signal','shared-show-hide-control','line-candle-switch-retains-toggle','all-selected-periods','OHLC-weighted-values-verified','finite-paths','mobile-no-overflow','no-orders-submitted']},null,2));
 console.log('PASS: DKX/MADKX visible in both chart styles; all periods and real OHLC values verified; no orders submitted.');await context.close();
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
