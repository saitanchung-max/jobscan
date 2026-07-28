# -*- coding: utf-8 -*-
# 合併三個掃描來源的中間檔 → data/latest_scan.json（Claude 排程任務每天讀這份）
import json, os, time

BASE = os.path.join(os.path.dirname(__file__), '..', 'data')
SOURCES = ['cake_new.json', '104_new.json', 'jobspy_new.json']

def main():
    merged, per_source, failed = [], {}, []
    seen_in_merge = set()
    for fn in SOURCES:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            failed.append(fn); per_source[fn] = 'missing'; continue
        try:
            d = json.load(open(p, encoding='utf-8'))
            per_source[fn] = {'scanned_at': d.get('scanned_at'), 'total_listed': d.get('total_listed'),
                              'new_count': d.get('new_count'), 'group_stats': d.get('group_stats')}
            for j in d.get('new_jobs') or []:
                u = (j.get('url') or '').split('?')[0].rstrip('/')
                if u and u not in seen_in_merge:
                    seen_in_merge.add(u)
                    merged.append(j)
        except Exception as e:
            failed.append(fn); per_source[fn] = f'parse_error: {str(e)[:100]}'
    out = {'merged_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'per_source': per_source, 'failed_sources': failed,
           'new_count': len(merged), 'new_jobs': merged}
    json.dump(out, open(os.path.join(BASE, 'latest_scan.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'merge: new={len(merged)} failed_sources={failed}')

if __name__ == '__main__':
    main()
