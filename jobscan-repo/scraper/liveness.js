// 追蹤中職缺死鏈檢查：讀 data/watch_urls.json，逐一判斷 open / closed / unknown
// 輸出 data/liveness.json
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const DATA = path.join(__dirname, '..', 'data');
const watch = JSON.parse(fs.readFileSync(path.join(DATA, 'watch_urls.json'), 'utf8'));

const CLOSED_PATTERNS = [
  '此職務已關閉', '此工作已關閉', '此職缺已關閉', '職缺已下架', '找不到這個工作',
  'no longer accepting applications', 'No longer accepting applications',
  'This job is no longer available', 'job is unavailable', '已停止招募',
  'Page not found', '找不到頁面',
];

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', locale: 'zh-TW' });
  const page = await ctx.newPage();
  const results = [];

  for (const w of watch) {
    const r = { url: w.url, company: w.company, title: w.title, status: 'unknown', evidence: null };
    try {
      const resp = await page.goto(w.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(3000);
      const code = resp ? resp.status() : 0;
      const text = await page.evaluate(() => document.body.innerText.slice(0, 20000));
      const hit = CLOSED_PATTERNS.find(p => text.includes(p));
      if (code === 404 || code === 410) { r.status = 'closed'; r.evidence = `HTTP ${code}`; }
      else if (hit) { r.status = 'closed'; r.evidence = `matched: ${hit}`; }
      else if (/linkedin\.com/.test(w.url) && /Sign in|authwall|加入 LinkedIn/i.test(text) && text.length < 3000) {
        r.status = 'unknown'; r.evidence = 'linkedin authwall';
      } else if (code >= 200 && code < 400 && text.length > 500) {
        r.status = 'open'; r.evidence = `HTTP ${code}, content ok`;
      } else { r.evidence = `HTTP ${code}, thin content`; }
    } catch (e) { r.evidence = `error: ${e.message.slice(0, 100)}`; }
    results.push(r);
    await page.waitForTimeout(1500);
  }
  await browser.close();

  const summary = results.reduce((a, r) => { a[r.status] = (a[r.status] || 0) + 1; return a; }, {});
  fs.writeFileSync(path.join(DATA, 'liveness.json'), JSON.stringify({
    checked_at: new Date().toISOString(), summary, results,
  }, null, 1));
  console.log('liveness summary:', JSON.stringify(summary));
})();
