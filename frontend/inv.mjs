import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
const bad = [];
for (const path of ['/daily-review','/watchlist','/quant-backtest','/correlation','/portfolios','/journal','/reports','/macro','/settings']) {
  await p.goto('http://127.0.0.1:5899'+path, { waitUntil: 'networkidle' });
  await p.waitForTimeout(3500);
  const r = await p.evaluate(() => {
    const issues = [];
    document.querySelectorAll('span').forEach(e => {
      if (e.children.length) return;
      const t=(e.textContent||'').trim();
      if (!/^[+-]\d[\d,]*\.?\d*%?$/.test(t)) return;
      const c = getComputedStyle(e).color.match(/\d+/g).map(Number);
      if (!c || c.length<3) return;
      const [red,g,bl] = c;
      const positive = t.startsWith('+'), negative = t.startsWith('-');
      const greenish = g > red + 15, reddish = red > g + 15;
      if (positive && greenish) issues.push({t, color:`${red},${g},${bl}`});
      if (negative && reddish) issues.push({t, color:`${red},${g},${bl}`});
    });
    return issues.slice(0,5);
  });
  if (r.length) bad.push({ path, r });
}
console.log(bad.length ? JSON.stringify(bad,null,1) : 'OK: 所有带符号数字的颜色方向正确');
await b.close();
