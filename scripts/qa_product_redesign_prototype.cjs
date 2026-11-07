/* Offline proposal QA only; this does not exercise the production application. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'output/product-redesign-2026-11-07');
const checks = [];
(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.PROTOTYPE_BROWSER || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: true, args: ['--disable-gpu']
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
    page.setDefaultTimeout(8000);
    const errors = [], requests = [];
    page.on('pageerror', error => errors.push(String(error)));
    page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
    const open = async () => page.goto(pathToFileURL(path.join(out, 'prototype.html')).href);
    const state = () => page.evaluate(() => window.productRedesignPrototype.getState());
    const action = name => page.locator(`[data-action="${name}"]`).filter({ visible: true }).first().click();
    const start = async () => { await open(); await page.getByRole('button', { name: '发现一个观察', exact: true }).click(); await action('open-case'); };
    const save = () => page.locator('#save-plan-button').click();
    const verify = () => page.locator('#verify-button').click();
    const check = (id, detail) => checks.push({ id, result: 'PASSED', detail });
    await start(); await save(); await verify();
    let s = await state();
    assert.equal(s.plan.contract, 'RB2701'); assert.equal(s.plan.evidence, 'E-DEMO-01'); assert.equal(s.plan.version, 1); assert.equal(s.verified, true);
    assert.equal(await page.locator('#risk-number').innerText(), '464元');
    await action('monitor'); await action('trigger'); s = await state();
    assert.equal(s.alert.planVersion, 1); assert.equal(s.simulation, null);
    await action('simulate'); s = await state();
    assert.equal(s.simulation.status, 'WAITING'); assert.equal(s.simulation.fills, 0); assert.equal(s.simulation.planVersion, 1);
    await action('finish'); await page.locator('#review-note').fill('原型QA：条件触发并不意味着成交，保留等待理由。'); await action('save-review');
    s = await state(); assert.equal(s.page, 'review'); assert.equal(s.review.planVersion, 1); assert.match(s.review.note, /保留等待理由/);
    check('Q01', '同一案例、证据和计划版本贯穿提醒、等待意图、复盘；触发没有生成成交。');
    await start(); await save(); await verify();
    await page.locator('#budget').fill('100');
    s = await state(); assert.equal(s.dirty, true); assert.equal(s.verified, false); assert.equal(await page.locator('#simulate-button').isDisabled(), true);
    await save(); await verify(); s = await state();
    assert.equal(s.plan.version, 2); assert.equal(s.pastPlans.length, 1); assert.equal(s.verified, false); assert.equal(await page.locator('#simulate-button').isDisabled(), true);
    check('Q02', '未保存修改和100元预算均阻止模拟就绪；保存保留旧版本。');
    await start(); await save(); await verify(); await action('fresh');
    s = await state(); assert.equal(s.fresh, false); assert.equal(s.verified, false); assert.equal(await page.locator('#simulate-button').isDisabled(), true);
    await action('fresh'); s = await state(); assert.equal(s.fresh, true); assert.equal(s.verified, false); assert.equal(await page.locator('#simulate-button').isDisabled(), true);
    await verify(); assert.equal((await state()).verified, true);
    check('Q03', '过时阻止就绪；恢复可用后仍需重新核验。');
    await page.locator('#contract-select').selectOption('RB2705');
    s = await state(); assert.equal(s.plan.contract, 'RB2701'); assert.equal(s.contract, 'RB2705'); assert.equal(s.verified, false); assert.equal(await page.locator('#verify-button').isDisabled(), true);
    await save(); s = await state(); assert.equal(s.plan.contract, 'RB2705'); assert.equal(s.plan.version, 2); assert.equal(s.pastPlans[0].contract, 'RB2701');
    check('Q04', '观察合约变化不会静默覆盖旧计划；显式保存新版本后保留原合约记录。');
    const beforeMode = await state(); await action('mode'); s = await state();
    assert.deepEqual(s.plan, beforeMode.plan); assert.deepEqual(s.draft, beforeMode.draft); assert.notEqual(s.pro, beforeMode.pro);
    check('Q05', '简洁/专业密度切换保留业务状态。');
    await start(); await save(); await verify();
    await action('mode');
    const pages = ['today', 'opportunities', 'desk', 'strategy', 'review'];
    const layouts = [];
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const name of pages) {
        await page.locator(`#nav-${name}`).click();
        const metrics = await page.evaluate(() => ({ viewport: innerWidth, width: document.documentElement.scrollWidth }));
        assert.ok(metrics.width <= metrics.viewport, `${name} overflow ${width}: ${metrics.width}`);
        layouts.push({ page: name, ...metrics });
      }
      await page.locator('#nav-desk').click();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: path.join(out, width === 1440 ? 'prototype-desktop.png' : 'prototype-mobile.png'), fullPage: false });
    }
    check('Q06', '五个入口在1440与390像素宽度下无页面横向溢出；已保存桌面/手机截图。');
    assert.equal(errors.length, 0); assert.equal(requests.length, 0);
    assert.match(await page.locator('#plan-form').innerText(), /跳空和滑点可能使损失超预算/);
    check('Q07', '无浏览器脚本错误、无HTTP请求；保护价情景试算边界可见。');
    const receipt = { scope: 'OFFLINE_PROTOTYPE_ONLY_NOT_PRODUCTION_OR_REAL_USER_VALIDATION', result: 'PASSED', checks, layouts, browserErrors: errors, httpRequests: requests, resolvedIssues: ['首次交互测试发现预算字段min=1、step=10使默认500被原生表单校验拦截；已将step改为1并重跑完整流程。'], productionTouched: false };
    fs.writeFileSync(path.join(out, 'prototype-qa.json'), JSON.stringify(receipt, null, 2) + '\n');
    console.log(JSON.stringify({ result: receipt.result, checks: checks.length, layouts: layouts.length, httpRequests: requests.length }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
