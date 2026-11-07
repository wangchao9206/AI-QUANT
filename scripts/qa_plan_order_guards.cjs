/* Full app/router UI checks. Every API response is a synthetic fixture; no production writes. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=path.resolve(__dirname,'../docs/implementation/plan-order-guards-2026-11-07');fs.mkdirSync(out,{recursive:true});
(async()=>{const browser=await chromium.launch({executablePath:process.env.PROTOTYPE_BROWSER||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}});page.setDefaultTimeout(15000);
 const errors=[],writes=[],checks=[],layouts=[];let variant='OWNER';
 page.on('pageerror',e=>errors.push(String(e)));page.on('console',m=>{if(m.type()==='error'&&/TypeError|Unhandled/.test(m.text()))errors.push(m.text())});
 const id='10000000-0000-4000-8000-000000000001',stamp='2026-11-06T07:00:00Z';
 function account(){const planGuard=variant==='UNLINKED'?{enabled:false}:variant==='OTHER'?{enabled:true,ownerVisible:false,openingAllowed:false,message:'此账户受私人计划约束；仅计划本人可新增开仓和撮合开仓挂单。可按原权限平仓或撤单。'}:{enabled:true,ownerVisible:true,openingAllowed:variant==='OWNER',version:2,side:'SHORT',lots:3,budget:1500,message:variant==='OWNER'?'新增开仓与成交均核对计划；行情及预算将在提交时重新核验。':'计划已过期：停止新增开仓，仍可平仓和撤单。'};
  return {id,name:'隔离计划账户',mode:'LIVE',status:'ACTIVE',symbol:'RB2701',currentContract:'RB2701',currentMarketTime:stamp,dataTimestamp:stamp,dataSource:'SYNTHETIC_FIXTURE',initialCash:100000,cashBalance:100000,equity:100000,realizedPnl:0,commissionPaid:0,slippagePaid:0,marginRate:.15,feeRate:0,slippageTicks:2,maxParticipationRate:.05,autoRoll:false,currentPrice:3200,currentBarIndex:0,totalBars:0,strategyId:'MANUAL',strategyLots:1,volumeMultiple:10,priceTick:1,marginPerLot:5000,commissionPerLot:3,position:{contract:'RB2701',marginOccupied:0,lots:0,direction:0,averagePrice:0,unrealizedPnl:0},orders:[],fills:[],planGuard,decisionGuarded:variant!=='UNLINKED'};
 }
 await page.route('**/api/**',async route=>{const req=route.request(),u=new URL(req.url());if(req.method()!=='GET')writes.push(u.pathname);let body;
  if(u.pathname==='/api/v1/auth/me')body={id:'10000000-0000-4000-8000-000000000009',tenantId:'10000000-0000-4000-8000-000000000010',username:'synthetic-plan-guard-qa',role:'MEMBER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:['market.read','paper.read','paper.write','overview.read'],menus:[{id:'paper',parentId:null,label:'模拟账本',path:'/paper',permission:'paper.read',sortOrder:1}]};
  else if(u.pathname==='/api/v1/paper/sessions')body=[account()];
  else if(u.pathname==='/api/v1/paper/sessions/'+id)body=account();
  else if(u.pathname.includes('/for-session/'))body={};
  else if(u.pathname.endsWith('/chart'))body={asOf:stamp,barIndex:0,source:'SYNTHETIC_FIXTURE',contextStatus:'READY',message:'隔离空图',bars:[],fills:[]};
  else if(/\/(orders|fills)$/.test(u.pathname))body={items:[],total:0,page:1,pageSize:20};
  else if(u.pathname==='/api/v1/backtest/presets')body={symbols:[{symbol:'RB0',name:'螺纹钢'}]};
  else if(u.pathname==='/api/v1/backtest/replay/status')body={totalSymbols:0,source:'SYNTHETIC_FIXTURE',message:'隔离空目录',symbols:[]};
  else return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({message:'隔离验收未提供此资料'})});
  return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
 });
 const base=process.env.PLAN_GUARD_UI_URL||'http://127.0.0.1:5179';
 async function open(){await page.goto(base+'/paper?session='+id);await page.locator('.submit-order').waitFor();}
 await open();const notice=page.getByRole('region',{name:'计划开仓约束'});await notice.waitFor();assert.ok((await notice.textContent()).includes('仅空头开仓'));assert.ok((await notice.textContent()).includes('最多 3 手'));assert.ok((await notice.textContent()).includes('不会自动止损或止盈'));assert.equal(await page.locator('.submit-order').isEnabled(),true);checks.push('本人可见方向、手数与预算，提交前说明实际服务端复核和非自动止损边界。');
 for(const width of [1440,390]){await page.setViewportSize({width,height:1100});await page.evaluate(()=>{scrollTo(0,0);let b=document.getElementById('qa-mark');if(!b){b=document.createElement('div');b.id='qa-mark';b.textContent='隔离验收 · 合成身份与账户 · 非实盘数据';b.style.cssText='position:fixed;bottom:0;left:0;right:0;background:#40235c;color:white;padding:7px;text-align:center;font:11px sans-serif;z-index:9999';document.body.append(b)}});const dimensions=await page.evaluate(()=>({viewport:innerWidth,width:document.documentElement.scrollWidth}));assert.ok(dimensions.width<=dimensions.viewport,JSON.stringify(dimensions));layouts.push(dimensions);await page.screenshot({path:path.join(out,`guard-fixture-${width}.png`)});}
 variant='EXPIRED';await open();assert.equal(await page.locator('.submit-order').isEnabled(),false);await page.locator('.order-ticket').getByRole('button',{name:'平仓',exact:true}).click();assert.equal(await page.locator('.submit-order').isEnabled(),true);checks.push('过期状态禁止新增开仓，切换平仓仍可提交，界面不把计划失效当成禁止离场。');
 variant='OTHER';await open();assert.ok(!(await notice.textContent()).includes('风险预算'));assert.ok(!(await notice.textContent()).includes('仅空头开仓'));assert.equal(await page.locator('.submit-order').isEnabled(),false);await page.locator('.order-ticket').getByRole('button',{name:'平仓',exact:true}).click();assert.equal(await page.locator('.submit-order').isEnabled(),true);checks.push('非本人不显示私人参数，禁止新增开仓，说明开仓挂单需本人核验及原平仓撤单权限。');
 variant='UNLINKED';await open();assert.equal(await notice.count(),0);assert.equal(await page.locator('.submit-order').isEnabled(),true);checks.push('未关联计划的普通模拟账户保留原手动下单入口。');
 assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
 fs.writeFileSync(path.join(out,'browser-qa.json'),JSON.stringify({scope:'FULL_APP_ROUTER_SYNTHETIC_IDENTITIES_AND_ACCOUNTS_NO_REAL_DATA_OR_WRITES',url:base,result:'PASSED',checks,layouts,errors,writeRequests:writes},null,2)+'\n');console.log(JSON.stringify({result:'PASSED',checks:checks.length,widths:layouts.length,errors:0,writes:0}));
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
