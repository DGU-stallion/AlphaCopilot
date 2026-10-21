import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
await p.goto('http://127.0.0.1:5899/daily-review', { waitUntil: 'networkidle' });
await p.waitForTimeout(4000);
const r = await p.evaluate(() => {
  const q = s => document.querySelector(s);
  const box = e => { if(!e) return null; const r=e.getBoundingClientRect(); return {t:Math.round(r.top),h:Math.round(r.height),b:Math.round(r.bottom)}; };
  const root = document.getElementById('root');
  const layout = root.firstElementChild;
  return {
    win: window.innerHeight,
    rootH: box(root)?.h,
    layoutTag: layout?.tagName + '.' + layout?.className,
    layoutBox: box(layout),
    layoutChildren: [...(layout?.children||[])].map(c => ({tag:c.tagName, cls:String(c.className).slice(0,40), ...box(c)})),
  };
});
console.log(JSON.stringify(r,null,1));
await b.close();
