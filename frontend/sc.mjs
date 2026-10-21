import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
await p.goto('http://127.0.0.1:5899/daily-review', { waitUntil: 'networkidle' });
await p.waitForTimeout(4000);
console.log(JSON.stringify(await p.evaluate(() => {
  const m = document.querySelector('[data-region="canvas"]');
  return { clientH: m.clientHeight, scrollH: m.scrollHeight, scrollable: m.scrollHeight > m.clientHeight };
})));
await p.evaluate(() => { document.querySelector('[data-region="canvas"]').scrollTop = 99999; });
await p.waitForTimeout(400);
await p.screenshot({ path: '/tmp/m5_scrolled.png' });
await b.close();
