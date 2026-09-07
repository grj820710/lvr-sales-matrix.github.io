# 實價登錄銷售矩陣自動更新

每週一 13:00（台北時間）從內政部開放資料抓指定建案的預售屋實價登錄，
重新產出互動版矩陣網頁，commit 回本 repo 並由 GitHub Pages 提供瀏覽。

## 建置步驟

1. 建立一個 repo，把本專案的檔案放進去 push 上去。

2. **Settings → Pages**，Source 選 `Deploy from a branch`，
   branch 選 `main`、資料夾選 `/docs`。存檔後網址會是
   `https://<帳號>.github.io/<repo 名稱>/`。

3. **Settings → Actions → General**，最下方 Workflow permissions
   選 `Read and write permissions`。少了這步驟排程可以跑，但推不回去。

4. 到 **Actions → 更新實價登錄資料 → Run workflow**，
   把 `backfill` 勾起來手動跑一次。這步會回補歷史季別，把資料建起來；
   之後的排程只抓當期，速度快很多。

## 追蹤別的建案

編輯 `projects.json`：

```json
{
  "slug": "fuwang-xinhaizhan",
  "name": "富旺心海綻",
  "county": "b",
  "title": "富旺心海綻",
  "subtitle": "臺中市沙鹿區"
}
```

- `name` 必須與實價登錄上的建案名稱**完全相符**，差一個字就抓不到。
- `county` 是縣市代碼字母，台中是 `b`，其餘見 `projects.json` 內的註解。
- `slug` 只能用英數與連字號，會變成網址的一部分。

改完 push 上去，下次排程就會自動納入；想立刻看到就手動觸發一次。

## 為什麼資料要累積在 data/

內政部的「當期」檔案只包含最近一次發布（每月 1、11、21 日）的登錄，
大約十天份。單看當期，一個建案通常只有零星幾筆甚至零筆。

所以 `scripts/update.py` 會把每次抓到的紀錄併進 `data/<slug>.json`，
以「建案＋棟及號＋交易日期＋總價」為鍵去重，長期累積出完整歷史。
這個 JSON 是會被 commit 的，等於是這個 repo 的資料庫，請不要隨手刪掉。

## 本機執行

```bash
pip install -r requirements.txt
python scripts/update.py --backfill   # 首次
python scripts/update.py              # 例行
```

產出在 `docs/`，直接用瀏覽器打開 `docs/index.html` 即可。

## 已知限制

- **下載端點未經實測。** 產出網頁與解析邏輯已用真實資料驗證過，但
  `scripts/moi_fetch.py` 裡的下載網址是依內政部目前的網站行為所寫，
  官方偶爾會調整參數。第一次跑 backfill 時請看 Actions 的日誌，
  若出現「回傳的不是 ZIP」，就到 <https://plvr.land.moi.gov.tw/DownloadOpenData>
  用瀏覽器開發者工具看實際送出的請求，對照修正 `moi_fetch.py` 裡的網址。
- 抓不到資料時腳本會保留既有頁面不覆蓋，不會把好好的頁面洗成空白。
- 預售屋登錄有申報期限，成交到出現在開放資料通常會落後一段時間。
- 解約案件仍會留在資料中並標示「已解約」，因為解約本身就是重要訊息。
