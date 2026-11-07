import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });
const errs=[]; p.on('pageerror', e=>errs.push(String(e).slice(0,150)));
await p.goto('http://127.0.0.1:5899/build', { waitUntil: 'networkidle' });
await p.waitForTimeout(4000);
// 改成不冲突的 slug 再点校验
const ta = await p.locator('textarea').first();
await ta.fill(JSON.stringify({slug:"build-preview-demo",title:"我的视图",kind:"user",status:"draft",layout:"grid",params:[],blocks:[{kind:"chart",span:2,renderer:"lwc",analysis_ref:{fn:"backtest.equity"}}]}, null, 2));
await p.getByText('校验并预览').click();
await p.waitForTimeout(5000);
const txt = await p.evaluate(()=>document.body.innerText);
console.log('含「校验通过」:', txt.includes('校验通过'));
console.log('含「预览」:', txt.includes('预览'));
await p.screenshot({ path: '/tmp/m5_build.png' });
console.log('errs:', errs.slice(0,3).join('\n')||'(none)');
await b.close();
