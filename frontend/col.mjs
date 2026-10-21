import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
await p.goto('http://127.0.0.1:5899/');
await p.evaluate(() => localStorage.setItem('vr-watchlist', JSON.stringify(['600519','300750'])));
await p.goto('http://127.0.0.1:5899/watchlist', { waitUntil: 'networkidle' });
await p.waitForTimeout(6000);
console.log(JSON.stringify(await p.evaluate(() => {
  const cs = getComputedStyle(document.documentElement);
  const cell = [...document.querySelectorAll('td')].find(td => /1,309\.69/.test(td.textContent||''));
  const pct = [...document.querySelectorAll('td')].find(td => /^\s*\+?1\.67%/.test(td.textContent||''));
  return {
    htmlCls: document.documentElement.className,
    danger: cs.getPropertyValue('--danger').trim(),
    success: cs.getPropertyValue('--success').trim(),
    upRaw: cs.getPropertyValue('--up-raw').trim(),
    cellCls: cell?.querySelector('span')?.className,
    cellInline: cell?.querySelector('span')?.getAttribute('style'),
    cellColor: cell ? getComputedStyle(cell.querySelector('span')).color : null,
    pctCls: pct?.querySelector('span')?.className,
    pctColor: pct ? getComputedStyle(pct.querySelector('span')).color : null,
  };
}), null, 1));
await b.close();
