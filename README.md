# 實價登錄銷售矩陣

把從「不動產交易實價查詢服務網」匯出的銷售表，轉成可互動的樓層／戶別矩陣網頁，
由 GitHub Pages 提供瀏覽。

## 日常流程

1. 到 <https://lvr.land.moi.gov.tw/> 查詢建案，把結果匯出成銷售表（.xls）
2. 把檔案放進 `sources/`，覆蓋掉舊的同名檔
3. commit 並 push

push 之後 GitHub Actions 會自動重新產出 `docs/`，Pages 隨即更新。
只有動到 `sources/`、`scripts/` 或 `projects.json` 才會觸發，不會每次 push 都跑。

## 加新建案

把匯出的 xls 放進 `sources/` 即可，檔名自取（建議用英文，會直接當成網址代號）。

想指定網址或顯示標題，就在 `projects.json` 加一筆：

```json
{
  "name": "富旺心海綻",
  "slug": "fuwang-xinhaizhan",
  "title": "富旺心海綻",
  "subtitle": "臺中市沙鹿區"
}
```

`name` 要與銷售表裡的建案名稱相符。沒列到的建案會用檔名當網址代號。

## 網址代號的產生規則

一律取自**檔名**（不是建案名稱），一律小寫：

| 檔名 | 產出 |
| --- | --- |
| `shengxing-fengchuan.xls` | `shengxing-fengchuan.html` |
| `My Project 2026.xls` | `my-project-2026.html` |
| `勝興豐川.xls` | `shengsingfongchuan.html` |
| `中文檔名測試.xlsx` | `jhongwundangmingceshih.html` |

含中文的檔名會轉成**通用拼音**，不帶聲調符號、不含空白。轉換規則依教育部
對照表實作（`scripts/tongyong.py`），聲母 zh→jh、q→c、x→s，並處理空韻
（shi→shih）、撮口呼（xu→syu）、韻母（-iu→-iou、-ui→-uei）與 feng→fong
等特例。已用高雄 gaosiong、新竹 sinjhu、淡水 danshuei 等官方譯名驗證。

`projects.json` 裡的 `slug` 會覆寫上述規則，優先權最高。

**改檔名等於改網址。** 舊網址不會自動保留轉址，`docs/` 底下的舊檔案也不會
自動刪除，需要時請自行清掉。

## 一格多筆

同一戶同一樓層可能有多筆登錄，最常見的是解約後重新出售。
矩陣格子顯示最新一筆並標示「共 N 筆」，點開後面板會由新到舊列出每一筆的
完整價格構成，舊的那筆仍保留解約標記。

頁面上方的「登錄筆數」是總筆數（不是格子數），可以直接跟實價登錄網站上的
數字對帳。產出時另有一道檢查：若有紀錄無法對應到表格位置，會在頁面上
顯示差額，不會靜默吞掉。

## 本機執行

```bash
pip install -r requirements.txt
python scripts/build.py
```

產出在 `docs/`，直接開 `docs/index.html` 即可預覽。

## 建置設定

- **Settings → Pages**：Source 選 `Deploy from a branch`，branch `main`、資料夾 `/docs`
- **Settings → Actions → General**：Workflow permissions 選 `Read and write permissions`
- `docs/.nojekyll` 不要刪。產出的是純 HTML，交給 Jekyll 反而會建置失敗。

## 為什麼用匯出檔而不是開放資料批次檔

批次檔（plvr 的 ZIP）分成當期、發布日、分季三種，彼此有覆蓋空窗：
當季尚未封存成季別檔，而當期只有最近十天，中間發布的交易兩邊都拿不到。
實測勝興豐川就因此少一筆。解約狀態也有同樣問題——解約是原交易發布後才申報的，
已封存的季別檔不會回頭更新。

匯出檔是網站當下的完整快照，筆數與解約狀態必然與畫面一致，代價只是需要手動匯出。
