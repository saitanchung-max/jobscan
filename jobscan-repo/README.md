# jobscan — 求職管線自動化 v2（Cake＋104＋LinkedIn/Indeed 掃描＋死鏈檢查）

這個 repo 是「找工作幫手!」專案的自動化外掛：用 GitHub Actions（有完整網路、
不受 Claude WebFetch 授權限制）每天掃三個來源的新職缺、每週檢查追蹤中職缺是否已關閉，
結果以 JSON 存回 repo，由 Claude 排程任務透過 raw.githubusercontent.com 讀取後處理。

## 掃描來源（v2）
1. **Cake** — Playwright 抓 8 組關鍵字搜尋頁（order=latest）＋新職缺 JD 內頁（JSON-LD）
2. **104** — 搜尋 JSON API（8 組關鍵字、雙北桃園、近7天）＋新職缺 JD 內文（ajax content API）
3. **LinkedIn / Indeed** — python-jobspy（LinkedIn 公開 guest API＋Indeed 台灣站，近72小時，含 JD）

三源各自輸出中間檔，`merge.py` 跨源去重合併成 `data/latest_scan.json`。
單一來源失敗不會擋住其他來源（workflow 各步驟 continue-on-error）。

## 結構
- `.github/workflows/scan.yml` — 每天台北 08:30 跑三源掃描＋合併（可手動觸發）
- `.github/workflows/liveness.yml` — 每週一台北 06:00 檢查 `data/watch_urls.json` 裡的職缺是否還活著（可手動觸發）
- `scraper/scan.js` — Cake 掃描（→ data/cake_new.json）
- `scraper/scan_104.py` — 104 掃描（→ data/104_new.json；關鍵字清單在檔案開頭，直接改）
- `scraper/scan_jobspy.py` — LinkedIn/Indeed 掃描（→ data/jobspy_new.json；關鍵字同上）
- `scraper/merge.py` — 跨源去重合併（→ data/latest_scan.json）
- `scraper/liveness.js` — 死鏈判斷（open / closed / unknown；LinkedIn 遇 authwall 標 unknown）
- `data/watch_urls.json` — 追蹤名單（由 Claude 產生，管線內容變動時換新檔）
- `data/latest_scan.json` — 每日掃描合併結果（Claude 每天讀這份）
- `data/liveness.json` — 死鏈檢查結果
- `data/seen_urls.json` — 已見過的職缺連結（三源共用，避免重抓 JD）

## 第一次設定（10 分鐘，全部在瀏覽器完成）
1. 註冊/登入 GitHub → 右上「＋」→「New repository」→ 名稱隨意（例如 `jobscan`）→
   **Public** → Create repository。
2. 在新 repo 頁面點「uploading an existing file」→ 把這個資料夾的**全部檔案連同資料夾結構**
   拖進去（`.github/workflows/` 兩個 yml 一定要在正確路徑）→ Commit。
   （如果拖曳無法保留資料夾，就用「Add file → Create new file」，檔名欄輸入
   `.github/workflows/scan.yml` 這樣的完整路徑再貼內容，逐檔建立。）
3. repo 上方「Actions」分頁 → 若出現啟用提示按啟用 →
   左側選 `weekly-liveness-check` → 右側「Run workflow」→ 跑完（約 5-10 分鐘）
   `data/liveness.json` 就會出現死鏈結果。
4. 同樣手動跑一次 `daily-job-scan` 確認能產出 `data/latest_scan.json`
   （首跑會抓三源全部現有職缺的 JD，時間較長屬正常；之後每天只抓新增的）。
5. 回 Claude 對話告訴我 repo 網址（例如 `https://github.com/你的帳號/jobscan`），
   我會接手：讀 liveness 結果標記 Notion、把每日排程任務改成全自動讀取掃描結果。

## 注意
- Public repo：內容只有公開職缺資訊與連結，無任何個人資料。不要把履歷等私人檔案放進來。
- 排程 cron 都是 UTC；GitHub 排程可能有幾分鐘到半小時的延遲，正常現象。
- Actions 免費額度對這個用量（每天一次幾分鐘）綽綽有餘。
