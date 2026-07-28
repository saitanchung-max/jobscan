# -*- coding: utf-8 -*-
# LinkedIn / Indeed 每日職缺掃描（GitHub Actions 環境執行）
# 使用 python-jobspy（LinkedIn 走公開 guest API；Indeed 台灣站）
# 輸出 data/jobspy_new.json，並把新連結加入 data/seen_urls.json
import json, os, re, time, sys

BASE = os.path.join(os.path.dirname(__file__), '..', 'data')
SEEN_PATH = os.path.join(BASE, 'seen_urls.json')

SEARCH_TERMS = ['business operations', 'chief of staff', 'strategy and operations',
                'digital transformation', 'AI implementation', '經營企劃', '策略規劃', 'AI導入']
LOCATION = 'Taipei, Taiwan'
HOURS_OLD = 72
RESULTS_PER_TERM = 25

def norm(u):
    if not u: return None
    u = u.split('?')[0].rstrip('/')
    m = re.search(r'linkedin\.com/jobs/view/(\d+)', u)
    if m: return f'https://www.linkedin.com/jobs/view/{m.group(1)}'
    return u

def load_seen():
    if os.path.exists(SEEN_PATH):
        return set(json.load(open(SEEN_PATH, encoding='utf-8')))
    return set()

def main():
    from jobspy import scrape_jobs
    seen = load_seen()
    by_url, stats = {}, {}
    for term in SEARCH_TERMS:
        for site in ('linkedin', 'indeed'):
            key = f'{site}:{term}'
            try:
                kwargs = dict(site_name=[site], search_term=term, location=LOCATION,
                              results_wanted=RESULTS_PER_TERM, hours_old=HOURS_OLD)
                if site == 'indeed':
                    kwargs['country_indeed'] = 'Taiwan'
                if site == 'linkedin':
                    kwargs['linkedin_fetch_description'] = True
                df = scrape_jobs(**kwargs)
                stats[key] = 0 if df is None else len(df)
                if df is None or df.empty:
                    continue
                for _, r in df.iterrows():
                    u = norm(str(r.get('job_url') or ''))
                    if not u: continue
                    if u not in by_url:
                        by_url[u] = {
                            'source': site, 'url': u,
                            'title': str(r.get('title') or ''),
                            'company': str(r.get('company') or ''),
                            'location': str(r.get('location') or ''),
                            'datePosted': str(r.get('date_posted') or ''),
                            'salary': (f"{r.get('min_amount')}-{r.get('max_amount')} {r.get('currency') or ''}".strip()
                                       if r.get('min_amount') == r.get('min_amount') else None),  # NaN check
                            'jd': re.sub(r'\s+', ' ', str(r.get('description') or ''))[:8000] or None,
                            'keywords': [term],
                        }
                    elif term not in by_url[u]['keywords']:
                        by_url[u]['keywords'].append(term)
            except Exception as e:
                stats[key] = f'ERROR: {str(e)[:100]}'
            time.sleep(2)

    fresh = [j for u, j in by_url.items() if u not in seen]
    for j in fresh: seen.add(j['url'])
    json.dump(sorted(seen), open(SEEN_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump({'source': 'jobspy(linkedin+indeed)',
               'scanned_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
               'group_stats': stats, 'total_listed': len(by_url), 'new_count': len(fresh),
               'new_jobs': fresh},
              open(os.path.join(BASE, 'jobspy_new.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f'jobspy: total={len(by_url)} new={len(fresh)}')

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'jobspy scan fatal: {e}', file=sys.stderr)
        sys.exit(0)
