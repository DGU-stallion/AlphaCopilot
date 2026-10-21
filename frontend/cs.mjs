import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
await p.goto('http://127.0.0.1:5899/daily-review', { waitUntil: 'networkidle' });
await p.waitForTimeout(4000);
const out = await p.evaluate(() => {
  const cs = getComputedStyle(document.documentElement);
  const els = [...document.querySelectorAll('span,div,b')].filter(e => /^\+?1\.68%/.test((e.textContent||'').trim()));
  const first = els[0];
  const s = first ? getComputedStyle(first) : null;
  return {
    htmlClass: document.documentElement.className,
    dangerVar: cs.getPropertyValue('--danger').trim(),
    upRaw: cs.getPropertyValue('--up-raw').trim(),
    downRaw: cs.getPropertyValue('--down-raw').trim(),
    text: (first?.textContent||'').slice(0,20),
    color: s?.color, cls: String(first?.className||'').slice(0,60),
  };
});
console.log(JSON.stringify(out, null, 1));
await b.close();
