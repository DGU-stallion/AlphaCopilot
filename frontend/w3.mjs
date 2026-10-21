import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
await p.goto('http://127.0.0.1:5899/');
await p.evaluate(() => localStorage.setItem('vr-watchlist', JSON.stringify(['600519'])));
await p.goto('http://127.0.0.1:5899/watchlist', { waitUntil: 'networkidle' });
await p.waitForTimeout(6000);
console.log(JSON.stringify(await p.evaluate(() => ({
  ls: localStorage.getItem('vr-watchlist'),
  bodyTail: document.body.innerText.slice(400, 900),
  hasChart: !!document.querySelector('[data-chart]'),
})) ,null,1));
await b.close();
