const { chromium } = require('/Users/a19150/Project/AlphaCopilot/frontend/node_modules/playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  await page.goto('file:///Users/a19150/Project/AlphaCopilot/docs/prototypes/d-b/index.html');
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'docs/prototypes/d-b/screenshot.png' });
  await browser.close();
})();
