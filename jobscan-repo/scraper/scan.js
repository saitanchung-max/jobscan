// Cake 每日職缺掃描（GitHub Actions 環境執行）
// 1) 抓 8 組搜尋頁（order=latest）→ 職缺清單
// 2) 對「未見過」的職缺連結抓 JD 內頁全文（JSON-LD JobPosting 優先）
// 3) 輸出 data/latest_scan.json（覆寫）＋ 更新 data/seen_urls.json
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const LOC = 'locations=%E5%8F%B0%E5%8C%97%E5%B8%82-%E5%8F%B0%E7%81%A3%2C%E6%96%B0%E5%8C%97%E5%B8%82-%E5%8F%B0%E7%81%A3%2C%E6%A1%83%E5%9C%92%E5%B8%82-%E5%8F%B0%E7%81%A3&job_types=full_time&order=latest';
const KEYWORDS = [
  ['策略規劃', `https://www.cake.me/jobs/%E7%AD%96%E7%95%A5%E8%A6%8F%E5%8A%83?${LOC}`],
  ['經營企劃', `https://www.cake.me/jobs/%E7%B6%93%E7%87%9F%E4%BC%81%E5%8A%83?${LOC}`],
  ['營運管理', `https://www.cake.me/jobs/%E7%87%9F%E9%81%8B%E7%AE%A1%E7%90%86?${LOC}`],
  ['business operations', `https://www.cake.me/jobs/business%20operations?${LOC}`],
  ['chief of staff', `https://www.cake.me/jobs/chief%20of%20staff?${LOC}`],
  ['數位轉型', `https://www.cake.me/jobs/%E6%95%B8%E4%BD%8D%E8%BD%89%E5%9E%8B?${LOC}`],
  ['AI導入', `https://www.cake.me/jobs/AI%E5%B0%8E%E5%85%A5?${LOC}`],
  ['AI implementation', `https://www.cake.me/jobs/AI%20implementation?${LOC}`],
];

const DATA = path.join(__dirname, '..', 'data');
const seenPath = path.join(DATA, 'seen_urls.json');
const seen = new Set(fs.existsSync(seenPath) ? JSON.parse(fs.readFileSync(seenPath, 'utf8')) : []);

const norm = (u) => u.split('?')[0].replace(/\/$/, '');

async function extractListings(page) {
  // Cake 是 Next.js：優先從 __NEXT_DATA__ 撈，fallback 掃 DOM anchors
  const fromNext = await page.evaluate(() => {
    const el = document.getElementById('__NEXT_DATA__');
    if (!el) return null;
    const out = [];
    const walk = (o) => {
      if (!o || typeof o !== 'object') return;
      if (Array.isArray(o)) { o.forEach(walk); return; }
      const title = o.title || o.name;
      const pth = o.path || o.page_path;
      const company = o.page && (o.page.name || o.page.title);
      if (title && pth && typeof pth === 'string') {
        out.push({ title, path: pth, company: company || o.company_name || null, location: (o.location_list && o.location_list[0]) || o.location || null });
      }
      Object.values(o).forEach(walk);
    };
    try { walk(JSON.parse(el.textContent)); } catch (e) { return null; }
    return out.length ? out : null;
  });
  if (fromNext) {
    return fromNext.map(j => ({
      title: j.title,
      company: j.company,
      location: typeof j.location === 'string' ? j.location : null,
      url: j.path.startsWith('http') ? j.path : `https://www.cake.me${j.path.startsWith('/') ? '' : '/'}${j.path}`,
    })).filter(j => /\/jobs\//.test(j.url));
  }
  // fallback: DOM anchors
  return page.evaluate(() => {
    const items = [];
    document.querySelectorAll('a[href*="/jobs/"]').forEach(a => {
      const href = a.href;
      if (!/cake\.me\/(companies\/[^/]+\/)?jobs\//.test(href)) return;
      const t = a.textContent.trim();
      if (t && t.length > 2 && t.length < 120) items.push({ title: t, company: null, location: null, url: href });
    });
    return items;
  });
}

async function extractJD(page) {
  return page.evaluate(() => {
    // JSON-LD JobPosting 優先
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      try {
        const arr = [].concat(JSON.parse(s.textContent));
        for (const d of arr) {
          if (d['@type'] === 'JobPosting') {
            const div = document.createElement('div');
            div.innerHTML = d.description || '';
            return {
              title: d.title || null,
              company: (d.hiringOrganization && d.hiringOrganization.name) || null,
              location: (() => { try { return d.jobLocation[0].address.addressLocality || d.jobLocation[0].address.addressRegion; } catch (e) { return null; } })(),
              datePosted: d.datePosted || null,
              validThrough: d.validThrough || null,
              salary: (() => { try { const v = d.baseSalary.value; return `${v.minValue || ''}-${v.maxValue || ''} ${d.baseSalary.currency || ''}`.trim(); } catch (e) { return null; } })(),
              jd: div.textContent.replace(/\s+/g, ' ').trim(),
            };
          }
        }
      } catch (e) { /* next */ }
    }
    // fallback：主內容區塊文字
    const main = document.querySelector('main') || document.body;
    return { title: document.title, company: null, location: null, datePosted: null, validThrough: null, salary: null, jd: main.innerText.replace(/\s+/g, ' ').trim().slice(0, 8000) };
  });
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36', locale: 'zh-TW' });
  const page = await ctx.newPage();

  const byUrl = new Map();
  const groupStats = {};
  for (const [kw, url] of KEYWORDS) {
    try {
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(3500);
      const listings = await extractListings(page);
      groupStats[kw] = listings.length;
      for (const j of listings) {
        const k = norm(j.url);
        if (!byUrl.has(k)) byUrl.set(k, { ...j, url: k, keywords: [kw] });
        else if (!byUrl.get(k).keywords.includes(kw)) byUrl.get(k).keywords.push(kw);
      }
    } catch (e) {
      groupStats[kw] = `ERROR: ${e.message.slice(0, 120)}`;
    }
    await page.waitForTimeout(1500);
  }

  // 只對「沒見過」的職缺抓 JD 內頁（控制量：單次上限 40 頁）
  const fresh = [...byUrl.values()].filter(j => !seen.has(j.url));
  let fetched = 0;
  for (const j of fresh) {
    if (fetched >= 40) { j.jd_note = 'detail_skipped_quota'; continue; }
    try {
      await page.goto(j.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
      await page.waitForTimeout(2500);
      const d = await extractJD(page);
      Object.assign(j, { company: j.company || d.company, location: j.location || d.location, datePosted: d.datePosted, validThrough: d.validThrough, salary: d.salary, jd: d.jd });
      fetched++;
    } catch (e) { j.jd_note = `detail_error: ${e.message.slice(0, 100)}`; }
    await page.waitForTimeout(1200);
  }
  await browser.close();

  fresh.forEach(j => seen.add(j.url));
  fs.writeFileSync(seenPath, JSON.stringify([...seen], null, 0));
  fs.writeFileSync(path.join(DATA, 'cake_new.json'), JSON.stringify({
    source: 'cake',
    scanned_at: new Date().toISOString(),
    group_stats: groupStats,
    total_listed: byUrl.size,
    new_count: fresh.length,
    new_jobs: fresh.map(j => ({ source: 'cake', ...j })),
  }, null, 1));
  console.log('groups:', JSON.stringify(groupStats));
  console.log(`total ${byUrl.size}, new ${fresh.length}, details fetched ${fetched}`);
})();
