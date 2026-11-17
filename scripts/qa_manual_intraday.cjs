/* Browser regression for the real Vue workspace; API responses are explicitly isolated fixtures. */
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('../.test-tmp/manual-replay-browser/node_modules/playwright');
const out=path.resolve(__dirname,'../.test-tmp/manual-intraday-qa');fs.mkdirSync(out,{recursive:true});
const archive=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../data/history/intraday-replay/FG701.json'),'utf8'));
const observed=archive.bars.slice(0,160),id='70000000-0000-4000-8000-000000000001';
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{const context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage();
let session=null,pending=null,note={content:'',version:0},fills=[],cursor=50;const errors=[];page.on('pageerror',e=>errors.push(String(e)));
await page.route('**/api/**',async route=>{const req=route.request(),u=new URL(req.url()),p=u.pathname;let body;
if(p==='/api/v1/auth/me')body={id,tenantId:id,username:'isolated-minute-qa',role:'OWNER',platformAdmin:false,mustChangePassword:false,tenants:[],permissions:['paper.read','paper.write','market.read'],menus:[{id:'paper',label:'模拟交易',path:'/paper',permission:'paper.read',parentId:null,sortOrder:1}]};
else if(p.startsWith('/api/v1/auth/workspace/'))body={revision:0,content:null};
else if(p==='/api/v1/paper/intraday/catalog')body={symbols:[{symbol:'FG701',name:'玻璃2701',exchange:'CZCE',sector:'分时回放',startDate:'2026-10-19',endDate:'2026-11-16',periods:[60,180,300,900]}],periods:[60,180,300,900],unavailable:[]};
else if(p==='/api/v1/data/replay/status')body={totalSymbols:0,symbols:[]};
else if(p.endsWith('/backtest/presets')||p.endsWith('/backtests/presets'))body={symbols:[],strategies:[]};
else if(p==='/api/v1/paper/sessions'&&req.method()==='GET')body=session?[session]:[];
else if(p==='/api/v1/paper/sessions'&&req.method()==='POST'){
 const b=req.postDataJSON();assert.equal(b.barSeconds,60);assert.equal(b.symbol,'FG701');assert.equal(b.autoRoll,false);
 session={...b,id,status:'ACTIVE',strategyId:'MANUAL',currentBarIndex:cursor,totalBars:observed.length,currentMarketTime:new Date(Date.parse(observed[cursor].timestamp)+60000).toISOString(),currentContract:'FG701',currentPrice:observed[cursor].close,volumeMultiple:20,priceTick:1,commissionPerLot:6,marginPerLot:1632.6,cashBalance:b.initialCash,equity:b.initialCash,initialCash:b.initialCash,version:1,dataSource:'ISOLATED_BROWSER_FIXTURE',position:{contract:'FG701',direction:0,lots:0,averagePrice:0,marginOccupied:0,unrealizedPnl:0},orders:[],activeOrders:[],fills:[],fillCount:0,orderCount:0,feesPaid:0,realizedPnl:0,slippagePaid:0};body=session;
}else if(p.endsWith('/note')){if(req.method()==='POST'){const b=req.postDataJSON();assert.equal(b.version,note.version);note={content:b.content,version:note.version+1,updatedAt:new Date().toISOString()}}body=note}
else if(p.endsWith('/advance')){cursor++;if(pending){fills=[{id:'70000000-0000-4000-8000-000000000002',side:'BUY',offset:'OPEN',eventType:'ORDER',contract:'FG701',quantity:1,marketPrice:observed[cursor].open,fillPrice:observed[cursor].open+1,fee:6,slippageCost:20,realizedPnl:0,marketTime:observed[cursor].timestamp,reason:'隔离浏览器验证'}];pending=null;session.position={...session.position,direction:1,lots:1,averagePrice:fills[0].fillPrice};session.activeOrders=[]}
 Object.assign(session,{currentBarIndex:cursor,currentMarketTime:new Date(Date.parse(observed[cursor].timestamp)+60000).toISOString(),currentPrice:observed[cursor].close,fills,fillCount:fills.length,version:session.version+1});body=session;
}else if(p.endsWith('/chart'))body={asOf:session.currentMarketTime,barIndex:cursor,barSeconds:60,source:'ISOLATED_BROWSER_FIXTURE',contextStatus:'READY',bars:observed.slice(0,cursor+1),fills,message:'已完成分钟K线'};
else if(p.endsWith('/records/fills'))body={page:1,pageSize:20,total:fills.length,items:fills};
else if(p.endsWith('/records/orders'))body={page:1,pageSize:20,total:0,items:[]};
else if(p.endsWith('/orders')&&req.method()==='POST'){pending=req.postDataJSON();session.activeOrders=[{...pending,id:'pending',remainingQuantity:1,status:'PENDING'}];body=session}
else if(p===`/api/v1/paper/sessions/${id}`)body=session;
else return route.fulfill({status:404,contentType:'application/json',body:'{"message":"隔离夹具未提供"}'});
return route.fulfill({contentType:'application/json',body:JSON.stringify(body)});
});
await page.goto(process.env.MANUAL_REPLAY_UI_URL||'http://127.0.0.1:5179/paper');
await page.getByLabel('回放K线周期').waitFor();assert.equal(await page.getByLabel('回放K线周期').inputValue(),'60');
await page.locator('.create-panel').screenshot({path:path.join(out,'create-desktop.png')});
await page.locator('.create-actions button').click();await page.locator('.tdx-trading-chart').waitFor();
await page.getByRole('button',{name:'提交买入开仓',exact:true}).click();assert.equal(fills.length,0);
await page.locator('button').filter({hasText:'单步'}).first().click();await page.getByRole('button',{name:'记录心得',exact:true}).waitFor();
await page.getByRole('button',{name:'记录心得',exact:true}).click();await page.getByLabel('我的心得与感悟').fill('先观察MA20与日线MACD，按计划入场，控制冲动。');
await page.getByRole('button',{name:'保存本笔心得',exact:true}).click();await page.getByRole('status').filter({hasText:'心得已保存'}).waitFor();
await page.screenshot({path:path.join(out,'journal-desktop.png'),fullPage:true});
await page.reload();await page.getByRole('button',{name:'记录心得',exact:true}).click();assert.equal(await page.getByLabel('我的心得与感悟').inputValue(),note.content);
await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'journal-mobile.png'),fullPage:true});
assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,'mobile overflow');assert.deepEqual(errors,[]);
console.log(JSON.stringify({status:'PASS',checks:['minute-create','next-bar-order','fill-journal-save','reload-persists','mobile-layout','no-page-errors'],out}));
await context.close();}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
