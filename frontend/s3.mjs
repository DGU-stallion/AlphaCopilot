import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });
const errs=[]; p.on('pageerror', e=>errs.push(String(e).slice(0,150)));
p.on('console', m=>{ if(m.type()==='error') errs.push('[c] '+m.text().slice(0,100)); });
await p.goto('http://127.0.0.1:5899/daily-review', { waitUntil: 'networkidle' });
await p.waitForTimeout(5000);
await p.screenshot({ path: '/tmp/m5_open.png' });
// 折叠 agent
await p.getByTitle('收起助手').click();
await p.waitForTimeout(600);
await p.screenshot({ path: '/tmp/m5_agent_closed.png' });
// 折叠导航
await p.getByTitle('收起导航').click();
await p.waitForTimeout(600);
await p.screenshot({ path: '/tmp/m5_both_closed.png' });
console.log('errs:', errs.slice(0,5).join('\n')||'(none)');
await b.close();
