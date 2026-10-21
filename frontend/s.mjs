import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 900 }, deviceScaleFactor: 2 });
const errs=[]; p.on('pageerror', e => errs.push(String(e).slice(0,250)));
await p.goto('http://127.0.0.1:5899/proto/app', { waitUntil: 'networkidle' });
await p.waitForTimeout(4500);
await p.screenshot({ path: '/tmp/v5.png' });
// 验证 pane 数量与对齐
const info = await p.evaluate(() => {
  const cs=[...document.querySelectorAll('canvas')].map(c=>{const r=c.getBoundingClientRect();return [Math.round(r.width),Math.round(r.height),Math.round(r.left)];});
  return cs;
});
console.log('canvases:', JSON.stringify(info));
console.log('errs:', errs.join('\n')||'(none)');
await b.close();
