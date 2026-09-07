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

- **`docs/.nojekyll` 不要刪。** GitHub Pages 預設會拿 Jekyll 去處理來源目錄，
  但本專案產出的是純 HTML，交給 Jekyll 只會出錯。這個空檔案就是關掉它的開關，
  `update.py` 每次執行也會確保它存在。同理，`docs/` 與 `data/` 底下的
  `index.html`、`.gitkeep` 也請保留 —— Git 不追蹤空資料夾，沒有它們的話
  這兩個目錄 push 上去會直接消失，Pages 會回報找不到目錄而建置失敗。
- **舊季別抓不到是正常的。** 官方的分季封存只免費開放最近幾季，較舊的季別
  不會回 404，而是把「系統簡介」那頁 HTML 吐回來。腳本會把這種情況判為
  「官方未開放此季別的免費下載，略過」，不當成錯誤。所以 backfill 能回補到
  多久以前，取決於官方當下開放幾季，不是設定問題。
- **查無資料會讓執行顯示失敗。** 若某個建案一筆都沒抓到，腳本會印出來源中
  名稱相近的建案供對照（多半是 `name` 少字或多字），並以非零狀態結束，
  避免「綠燈但其實什麼都沒更新」。
- 抓不到資料時腳本會保留既有頁面不覆蓋，不會把好好的頁面洗成空白。
- 預售屋登錄有申報期限，成交到出現在開放資料通常會落後一段時間。
- 解約案件仍會留在資料中並標示「已解約」，因為解約本身就是重要訊息。
