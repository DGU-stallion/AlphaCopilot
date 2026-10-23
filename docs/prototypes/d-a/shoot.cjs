const { chromium } = require('/Users/a19150/Project/AlphaCopilot/frontend/node_modules/playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto('file:///Users/a19150/Project/AlphaCopilot/docs/prototypes/d-a/index.html');
  await page.waitForTimeout(300);
  // 溢出检测
  const overflow = await page.evaluate(() => {
    const issues = [];
    if (document.documentElement.scrollWidth > 1440) issues.push(`H scroll: ${document.documentElement.scrollWidth}`);
    if (document.documentElement.scrollHeight > 900) issues.push(`V scroll: ${document.documentElement.scrollHeight}`);
    // 检查所有元素是否超出视口
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > 1441 || r.bottom > 901 || r.left < -1 || r.top < -1) {
        issues.push(`${el.tagName}.${el.className && el.className.baseVal !== undefined ? '' : (el.className||'')} out of viewport: l=${Math.round(r.left)} t=${Math.round(r.top)} r=${Math.round(r.right)} b=${Math.round(r.bottom)}`);
      }
    }
    return issues;
  });
  if (overflow.length) console.log('OVERFLOW ISSUES:\n' + overflow.join('\n'));
  else console.log('No overflow.');
  await page.screenshot({ path: '/Users/a19150/Project/AlphaCopilot/docs/prototypes/d-a/screenshot.png' });
  await browser.close();
  console.log('Screenshot saved.');
})();
