# -*- coding: utf-8 -*-
# 合併三個掃描來源的中間檔 → data/latest_scan.json（Claude 排程任務每天讀這份）
import json, os, time

BASE = os.path.join(os.path.dirname(__file__), '..', 'data')
SOURCES = ['cake_new.json', '104_new.json', 'jobspy_new.json']

def count_bad_keywords(group_stats):
    """group_stats 裡有幾組關鍵字明顯異常：ERROR/BLOCKED 字串，或診斷物件裡 count=0。"""
    if not isinstance(group_stats, dict):
        return 0
    bad = 0
    for v in group_stats.values():
        if isinstance(v, str) and (v.startswith('ERROR') or v.startswith('BLOCKED')):
            bad += 1
        elif isinstance(v, dict) and v.get('count', 1) == 0:
            bad += 1
    return bad

def main():
    merged, per_source, failed, warnings = [], {}, [], []
    seen_in_merge = set()
    for fn in SOURCES:
        p = os.path.join(BASE, fn)
        if not os.path.exists(p):
            failed.append(fn); per_source[fn] = 'missing'; continue
        try:
            d = json.load(open(p, encoding='utf-8'))
            gs = d.get('group_stats')
            total_listed = d.get('total_listed')
            per_source[fn] = {'scanned_at': d.get('scanned_at'), 'total_listed': total_listed,
                              'new_count': d.get('new_count'), 'group_stats': gs}
            n_keywords = len(gs) if isinstance(gs, dict) else 0
            n_bad = count_bad_keywords(gs)
            if total_listed == 0 and n_keywords > 0:
                warnings.append(f"{fn}: total_listed=0，橫跨全部 {n_keywords} 組關鍵字 — 極可能是被封鎖或解析失敗，不是真的零筆新職缺")
            elif n_keywords and n_bad == n_keywords:
                warnings.append(f"{fn}: 全部 {n_keywords} 組關鍵字回報錯誤/零筆")
            elif n_bad > 0:
                warnings.append(f"{fn}: {n_bad}/{n_keywords} 組關鍵字回報錯誤/零筆，其餘正常")
            for j in d.get('new_jobs') or []:
                u = (j.get('url') or '').split('?')[0].rstrip('/')
                if u and u not in seen_in_merge:
                    seen_in_merge.add(u); merged.append(j)
        except Exception as e:
            failed.append(fn); per_source[fn] = f'parse_error: {str(e)[:100]}'
    out = {'merged_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'per_source': per_source, 'failed_sources': failed,
           'health_warnings': warnings,
           'new_count': len(merged), 'new_jobs': merged}
    json.dump(out, open(os.path.join(BASE, 'latest_scan.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'merge: new={len(merged)} failed_sources={failed} health_warnings={warnings}')

    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary_path:
        with open(summary_path, 'a', encoding='utf-8') as f:
            f.write(f"\n## 掃描健康度 — {out['merged_at']}\n\n")
            f.write(f"- 合併後新職缺：**{len(merged)}** 筆\n")
            if failed:
                f.write(f"- 完全失敗的來源：{', '.join(failed)}\n")
            if warnings:
                f.write("- 健康度警告：\n")
                for w in warnings:
                    f.write(f"  - {w}\n")
            if not failed and not warnings:
                f.write("- 三源皆正常\n")

if __name__ == '__main__':
    main()
