import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
await p.goto('http://127.0.0.1:5899/daily-review', { waitUntil: 'networkidle' });
await p.waitForTimeout(4000);
const out = await p.evaluate(() => {
  const spans = [...document.querySelectorAll('span')].filter(e => {
    const t=(e.textContent||'').trim();
    return /^\+?\d+\.\d{2}%$/.test(t) && e.children.length===0;
  });
  return spans.slice(0,6).map(e => ({ t:(e.textContent||'').trim(), color:getComputedStyle(e).color,
    fam:getComputedStyle(e).fontFamily.split(',')[0], inline:e.getAttribute('style')||'' }));
});
console.log(JSON.stringify(out,null,1));
await b.close();
