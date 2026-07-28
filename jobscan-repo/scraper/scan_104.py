# -*- coding: utf-8 -*-
# 104 每日職缺掃描（GitHub Actions 環境執行）
# 走 104 搜尋 JSON API（需正確 Referer header），對新職缺抓 JD 內文
# 輸出 data/104_new.json，並把新連結加入 data/seen_urls.json
import json, os, re, time, sys
import requests

BASE = os.path.join(os.path.dirname(__file__), '..', 'data')
SEEN_PATH = os.path.join(BASE, 'seen_urls.json')

KEYWORDS = ['策略規劃', '經營企劃', '營運管理', '數位轉型', 'AI導入', '幕僚', '策略幕僚', 'business operations']
# 台北市 6001001000 / 新北市 6001002000 / 桃園市 6001005000
AREA = '6001001000,6001002000,6001005000'
ISNEW = '7'          # 最近 7 天內更新
MAX_PAGES = 2        # 每關鍵字最多 2 頁（每頁約 20-30 筆，order=latest 情境下夠用）
DETAIL_QUOTA = 40    # 單次最多抓幾筆 JD 內文

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
    'Referer': 'https://www.104.com.tw/jobs/search/',
    'Accept': 'application/json',
}

def norm(u):
    return u.split('?')[0].rstrip('/')

def load_seen():
    if os.path.exists(SEEN_PATH):
        return set(json.load(open(SEEN_PATH, encoding='utf-8')))
    return set()

def search(keyword, page):
    url = 'https://www.104.com.tw/jobs/search/list'
    params = {'ro': '0', 'kwop': '7', 'keyword': keyword, 'area': AREA,
              'isnew': ISNEW, 'mode': 's', 'page': str(page), 'jobsource': '2018indexpoc'}
    r = requests.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()

def job_id_from_link(link):
    m = re.search(r'//www\.104\.com\.tw/job/([a-z0-9]+)', link)
    return m.group(1) if m else None

def fetch_detail(job_id):
    url = f'https://www.104.com.tw/job/ajax/content/{job_id}'
    h = dict(HEADERS); h['Referer'] = f'https://www.104.com.tw/job/{job_id}'
    r = requests.get(url, headers=h, timeout=30)
    r.raise_for_status()
    d = r.json().get('data', {})
    jd = d.get('jobDetail', {})
    cond = d.get('condition', {})
    return {
        'jd': re.sub(r'\s+', ' ', (jd.get('jobDescription') or '')).strip(),
        'salary': jd.get('salary'),
        'other': re.sub(r'\s+', ' ', (cond.get('other') or '')).strip(),
        'edu': cond.get('edu'), 'work_exp': cond.get('workExp'),
        'major': '、'.join(cond.get('major') or []) if isinstance(cond.get('major'), list) else cond.get('major'),
    }

def main():
    seen = load_seen()
    by_url, stats = {}, {}
    for kw in KEYWORDS:
        cnt = 0
        for page in range(1, MAX_PAGES + 1):
            try:
                data = search(kw, page)
                items = (data.get('data') or {}).get('list') or []
            except Exception as e:
                stats[kw] = f'ERROR: {str(e)[:100]}'; items = []
            if not items:
                break
            for it in items:
                link = it.get('link', {}).get('job') or ''
                if link.startswith('//'): link = 'https:' + link
                jid = job_id_from_link(link)
                if not jid: continue
                u = f'https://www.104.com.tw/job/{jid}'
                cnt += 1
                if u not in by_url:
                    by_url[u] = {'source': '104', 'url': u, 'title': it.get('jobName'),
                                 'company': it.get('custName'), 'location': it.get('jobAddrNoDesc'),
                                 'datePosted': it.get('appearDate'), 'keywords': [kw]}
                elif kw not in by_url[u]['keywords']:
                    by_url[u]['keywords'].append(kw)
            time.sleep(1.5)
        stats.setdefault(kw, cnt)

    fresh = [j for u, j in by_url.items() if u not in seen]
    fetched = 0
    for j in fresh:
        if fetched >= DETAIL_QUOTA:
            j['jd_note'] = 'detail_skipped_quota'; continue
        try:
            j.update(fetch_detail(job_id_from_link(j['url'] + '/')  or j['url'].rsplit('/', 1)[-1]))
            fetched += 1
        except Exception as e:
            j['jd_note'] = f'detail_error: {str(e)[:100]}'
        time.sleep(1.2)

    for j in fresh: seen.add(j['url'])
    json.dump(sorted(seen), open(SEEN_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump({'source': '104', 'scanned_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'group_stats': stats, 'total_listed': len(by_url), 'new_count': len(fresh),
               'new_jobs': fresh},
              open(os.path.join(BASE, '104_new.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'104: groups={stats} total={len(by_url)} new={len(fresh)} details={fetched}')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'104 scan fatal: {e}', file=sys.stderr)
        sys.exit(0)  # 不讓單源失敗擋住整條 workflow
