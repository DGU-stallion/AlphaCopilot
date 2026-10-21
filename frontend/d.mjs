import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 } });
const logs=[]; p.on('console', m=>logs.push(m.type()+': '+m.text().slice(0,150)));
p.on('pageerror', e=>logs.push('ERR: '+String(e).slice(0,200)));
await p.goto('http://127.0.0.1:5899/watchlist', { waitUntil: 'networkidle' });
await p.waitForTimeout(5000);
const t = await p.evaluate(() => {
  const panels=[...document.querySelectorAll('div')].filter(d=>/K 线|日线/.test(d.textContent||'') && d.className.includes('rounded'));
  return { text: document.body.innerText.slice(0,600), chartDiv: !!document.querySelector('[data-chart="price"]') };
});
console.log(JSON.stringify(t,null,1).slice(0,900));
console.log(logs.slice(0,6).join('\n'));
await b.close();
