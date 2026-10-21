import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });
const errs=[]; p.on('pageerror', e=>errs.push(String(e).slice(0,250)));
p.on('console', m=>{ if(m.type()==='error') errs.push('[c] '+m.text().slice(0,150)); });
await p.goto('http://127.0.0.1:5899/');
await p.evaluate(() => localStorage.setItem('vr-watchlist', JSON.stringify(['600519','000858','300750'])));
await p.goto('http://127.0.0.1:5899/watchlist', { waitUntil: 'networkidle' });
await p.waitForTimeout(7000);
const geo = await p.evaluate(() => {
  const box = document.querySelector('[data-chart="price"]');
  if (!box) return { found: false };
  const cs = [...box.querySelectorAll('canvas')].map(c => {
    const r = c.getBoundingClientRect();
    return { l: Math.round(r.left), t: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
  });
  return { found: true, boxH: Math.round(box.getBoundingClientRect().height), canvases: cs };
});
console.log(JSON.stringify(geo, null, 1));
await p.screenshot({ path: '/tmp/m6_watchlist.png' });
console.log('errs:', errs.slice(0,4).join('\n')||'(none)');
await b.close();
