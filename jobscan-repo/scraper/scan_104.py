# -*- coding: utf-8 -*-
# 104 每日職缺掃描（GitHub Actions 環境執行）
# 走 104 搜尋 JSON API（需正確 Referer/Accept header），對新職缺抓 JD 內文
# 輸出 data/104_new.json，並把新連結加入 data/seen_urls.json
#
# 已知限制：GitHub Actions runner 用的是雲端機房 IP（Azure/AWS 網段），
# 104 對這類 ASN 的封鎖很可能是位址層級的，不是單純 header 不對就能解。
# 這版加強了 session 預熱＋更完整的瀏覽器 header＋重試，
# 但若持續 403，代表封鎖在 IP 層，需要人工到瀏覽器查證這批職缺是否還在。
import json, os, re, time, sys
import requests

BASE = os.path.join(os.path.dirname(__file__), '..', 'data')
SEEN_PATH = os.path.join(BASE, 'seen_urls.json')

KEYWORDS = ['策略規劃', '經營企劃', '營運管理', '數位轉型', 'AI導入', '幕僚', '策略幕僚', 'business operations']
AREA = '6001001000,6001002000,6001005000'
ISNEW = '7'
MAX_PAGES = 2
DETAIL_QUOTA = 40
MAX_RETRIES = 2
RETRY_BACKOFF = 4  # 秒，乘以重試次數

BASE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'sec-ch-ua': '"Chromium";v="126", "Not.A/Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}

class Blocked(Exception):
    pass

def make_session():
    """預熱 session：先訪問搜尋首頁拿 cookie，比冷啟動直接打 API 更接近真實瀏覽行為。"""
    s = requests.Session()
    s.headers.update(BASE_HEADERS)
    try:
        s.get('https://www.104.com.tw/jobs/search/', timeout=20)
    except Exception:
        pass
    time.sleep(1.5)
    return s

def norm(u):
    return u.split('?')[0].rstrip('/')

def load_seen():
    if os.path.exists(SEEN_PATH):
        return set(json.load(open(SEEN_PATH, encoding='utf-8')))
    return set()

def _request_json(session, url, params, headers):
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = session.get(url, params=params, headers=headers, timeout=30)
            ctype = r.headers.get('content-type', '')
            if r.status_code == 403 or 'application/json' not in ctype:
                raise Blocked(f'HTTP {r.status_code}, content-type={ctype or "?"}')
            r.raise_for_status()
            return r.json()
        except Blocked as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            raise
    raise last_err

def search(session, keyword, page):
    url = 'https://www.104.com.tw/jobs/search/list'
    params = {'ro': '0', 'kwop': '7', 'keyword': keyword, 'area': AREA,
              'isnew': ISNEW, 'mode': 's', 'page': str(page), 'jobsource': '2018indexpoc'}
    h = dict(session.headers)
    h.update({'Referer': 'https://www.104.com.tw/jobs/search/', 'Accept': 'application/json',
              'X-Requested-With': 'XMLHttpRequest'})
    return _request_json(session, url, params, h)

def job_id_from_link(link):
    m = re.search(r'//www\.104\.com\.tw/job/([a-z0-9]+)', link)
    return m.group(1) if m else None

def fetch_detail(session, job_id):
    url = f'https://www.104.com.tw/job/ajax/content/{job_id}'
    h = dict(session.headers)
    h.update({'Referer': f'https://www.104.com.tw/job/{job_id}', 'Accept': 'application/json',
              'X-Requested-With': 'XMLHttpRequest'})
    d = _request_json(session, url, None, h).get('data', {})
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
    session = make_session()
    by_url, stats = {}, {}
    for kw in KEYWORDS:
        cnt = 0
        for page in range(1, MAX_PAGES + 1):
            try:
                data = search(session, kw, page)
                items = (data.get('data') or {}).get('list') or []
            except Blocked as e:
                stats[kw] = f'BLOCKED: {str(e)[:100]}'; items = []
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
            time.sleep(2)
        stats.setdefault(kw, cnt)

    fresh = [j for u, j in by_url.items() if u not in seen]
    fetched = 0
    for j in fresh:
        if fetched >= DETAIL_QUOTA:
            j['jd_note'] = 'detail_skipped_quota'; continue
        try:
            j.update(fetch_detail(session, job_id_from_link(j['url'] + '/') or j['url'].rsplit('/', 1)[-1]))
            fetched += 1
        except Blocked as e:
            j['jd_note'] = f'blocked: {str(e)[:100]}'
        except Exception as e:
            j['jd_note'] = f'detail_error: {str(e)[:100]}'
        time.sleep(1.5)

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
        sys.exit(0)
