import { chromium } from 'playwright';
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1600, height: 950 }, deviceScaleFactor: 2 });
await p.goto('http://127.0.0.1:5899/daily-review', { waitUntil: 'networkidle' });
await p.waitForTimeout(3000);
// 切深色：点左下角
await p.getByText('暗色').click();
await p.waitForTimeout(2500);
await p.screenshot({ path: '/tmp/m2_dark2.png' });
await b.close();
