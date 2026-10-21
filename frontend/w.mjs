import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });
const errs=[]; p.on('pageerror', e=>errs.push(String(e).slice(0,200)));
p.on('console', m=>{ if(m.type()==='error') errs.push('[c] '+m.text().slice(0,150)); });
await p.goto('http://127.0.0.1:5899/watchlist', { waitUntil: 'networkidle' });
await p.waitForTimeout(6000);
// 量 pane 与 K 线 pane 是否左对齐
const geo = await p.evaluate(() => {
  const box = document.querySelector('[data-chart="price"]');
  const cs = [...(box?.querySelectorAll('canvas')||[])].map(c => {
    const r = c.getBoundingClientRect();
    return { l: Math.round(r.left), w: Math.round(r.width), cls: c.className.slice(0,20) };
  });
  return { boxH: Math.round(box?.getBoundingClientRect().height||0), cs };
});
console.log(JSON.stringify(geo));
await p.screenshot({ path: '/tmp/m6_watchlist.png' });
console.log('errs:', errs.slice(0,4).join('\n')||'(none)');
await b.close();
