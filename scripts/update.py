"""
主流程：下載 → 解析 → 併入既有資料 → 產出網頁。

資料是「累積」的：每次執行把新抓到的紀錄併進 data/{slug}.json，
用 key（建案+棟及號+交易日期+總價）去重。因為當期檔只含最近十天，
不累積的話每次產出的頁面都只會有寥寥幾筆。

用法：
    python scripts/update.py              # 例行更新（當期 + 最近一季）
    python scripts/update.py --backfill   # 首次建立，回補多季
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import build_site
import moi_fetch
import moi_parse

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DOCS = ROOT / "docs"


def load_store(slug: str) -> dict[str, dict]:
    path = DATA / f"{slug}.json"
    if not path.exists():
        return {}
    return {r["key"]: r for r in json.loads(path.read_text(encoding="utf-8"))}


def save_store(slug: str, store: dict[str, dict]) -> None:
    DATA.mkdir(exist_ok=True)
    rows = sorted(store.values(), key=lambda r: (r["unit"], -r["floor"], r["raw_date"]))
    (DATA / f"{slug}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true", help="回補歷史季別（首次執行用）")
    ap.add_argument("--dump", action="store_true",
                    help="印出來源檔的表頭與每一筆原始欄位，用於跟實價登錄網站對帳")
    args = ap.parse_args()

    config = json.loads((ROOT / "projects.json").read_text(encoding="utf-8"))
    projects = config["projects"]

    n_seasons = config.get("backfill_seasons", 8) if args.backfill else 2
    n_months = config.get("publish_months", 6) if not args.backfill else 12

    # 來源必須「舊到新」排列。同一筆交易若在後續批次被更新（最常見的是補上
    # 解約情形），合併時要讓較新的快照覆蓋較舊的；順序顛倒會反過來把解約洗掉。
    zips = []
    for season in reversed(moi_fetch.recent_seasons(n_seasons)):
        res = moi_fetch.fetch_season(season)
        if res.zf:
            zips.append((season, res.zf))

    # 分季檔只到上一季，當季要靠發布日檔案補。這也是取得解約更新的唯一途徑。
    for ymd in moi_fetch.publish_dates(n_months):
        res = moi_fetch.fetch_history(ymd)
        if res.zf:
            zips.append((f"發布日{ymd}", res.zf))

    res = moi_fetch.fetch_current()
    if res.zf:
        zips.append(("current", res.zf))

    if not zips:
        print("沒有抓到任何資料來源，中止（保留現有頁面不動）。")
        return 1
    print(f"可用資料來源 {len(zips)} 個（舊到新）："
          f"{', '.join(label for label, _ in zips)}")

    DOCS.mkdir(exist_ok=True)
    # 產出的是純 HTML，讓 GitHub Pages 跳過 Jekyll。這個檔案若不在，
    # Pages 會用 Jekyll 去處理 docs/，反而可能建置失敗。
    (DOCS / ".nojekyll").touch()
    index_rows = []
    failed = False

    for proj in projects:
        slug = proj["slug"]
        store = load_store(slug)
        before = len(store)

        for label, zf in zips:
            try:
                found = moi_parse.extract(zf, proj["county"], proj["name"])
            except Exception as exc:  # noqa: BLE001
                print(f"  [{slug}] 解析 {label} 失敗：{exc}")
                failed = True
                continue
            for rec in found:
                store[rec["key"]] = rec

        added = len(store) - before
        print(f"[{slug}] {proj['name']}：共 {len(store)} 筆（本次新增 {added}）")

        # 逐筆列出，方便直接跟實價登錄網站上的筆數與內容對帳。
        # 筆數對不上時，這份清單是唯一能看出差在哪裡的東西。
        n_cancel = sum(1 for r in store.values() if r["cancelled"])
        print(f"  其中標記已解約 {n_cancel} 筆")
        for r in sorted(store.values(), key=lambda x: (x["unit"], -x["floor"], x["raw_date"])):
            flag = " [解約]" if r["cancelled"] else ""
            print(f"    {r['unit']:>6} {r['floor']:>3}F  {r['full_date']}  "
                  f"{r['total_price']:>8,.0f}萬  {r['unit_price']:>6.2f}萬/坪  "
                  f"棟及號={r['dong_hao']}{flag}")

        if args.dump:
            _dump_raw(zips, proj)

        if not store:
            # 查無資料通常代表建案名稱對不上，或這幾個來源剛好沒有這個建案的登錄。
            # 不寫檔以免把既有頁面洗白，但要讓這次執行顯示為失敗，否則會像成功。
            print(f"  [{slug}] 查無資料。請確認 projects.json 的 name "
                  f"與實價登錄上的建案名稱完全相符，且 county 代碼正確。")
            _hint_names(zips, proj)
            failed = True
            continue

        save_store(slug, store)
        page = build_site.build(proj, list(store.values()))
        (DOCS / f"{slug}.html").write_text(page, encoding="utf-8")
        index_rows.append((proj, len(store)))

    if index_rows:
        (DOCS / "index.html").write_text(_index(index_rows), encoding="utf-8")

    return 1 if failed else 0


def _dump_raw(zips, proj) -> None:
    """印出來源主檔的表頭，以及此建案每一列的原始欄位值。

    用途：當產出的筆數與實價登錄網站不符時，先確認
    (1) 表頭欄名是否與程式模糊比對的關鍵字一致
    (2) 開放資料裡到底有幾列、解約情形這欄實際存的是什麼
    """
    import moi_parse as mp
    names = mp.presale_filenames(proj["county"])
    for label, zf in zips:
        if names["main"] not in set(zf.namelist()):
            print(f"  [dump] {label}：找不到 {names['main']}，"
                  f"此來源的檔案有 {len([n for n in zf.namelist() if n.endswith('.csv')])} 個 CSV")
            continue
        rows = mp._read_csv(zf, names["main"])
        mine = [r for r in rows if mp._pick(r, "建案名稱").strip() == proj["name"]]
        print(f"  [dump] {label}：{names['main']} 共 {len(rows)} 列，"
              f"其中建案名稱相符 {len(mine)} 列")
        if rows:
            print(f"  [dump] 表頭：{' | '.join(rows[0].keys())}")
        for r in mine:
            print(f"  [dump] 棟及號={mp._pick(r, '棟及號')!r} "
                  f"交易年月日={mp._pick(r, '交易年月日')!r} "
                  f"總價元={mp._pick(r, '總價元', '總價')!r} "
                  f"移轉層次={mp._pick(r, '移轉層次')!r} "
                  f"解約情形={mp._pick(r, '解約情形')!r}")


def _hint_names(zips, proj) -> None:
    """查無資料時，把來源裡名字相近的建案列出來，方便對照是不是名稱寫錯。"""
    import moi_parse as mp
    seen = set()
    needle = proj["name"][:2]
    for _, zf in zips:
        names = mp.presale_filenames(proj["county"])
        if names["main"] not in set(zf.namelist()):
            continue
        for row in mp._read_csv(zf, names["main"]):
            nm = mp._pick(row, "建案名稱").strip()
            if nm and needle in nm:
                seen.add(nm)
    if seen:
        print(f"  [{proj['slug']}] 來源中名稱相近的建案："
              + "、".join(sorted(seen)[:10]))
    else:
        print(f"  [{proj['slug']}] 來源中找不到含「{needle}」的建案名稱。")


def _index(rows) -> str:
    items = "\n".join(
        f'<li><a href="{p["slug"]}.html">{p.get("title", p["name"])}</a>'
        f'<span class="n">{n} 筆登錄</span></li>' for p, n in rows)
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>實價登錄銷售矩陣</title><style>
body{{font-family:"Noto Sans TC","PingFang TC",sans-serif;background:#f4f5f7;margin:0;
padding:32px 18px;color:#333}}.wrap{{max-width:640px;margin:0 auto}}
h1{{font-size:20px;color:#1f2d3d;margin:0 0 16px}}
ul{{list-style:none;padding:0;margin:0}}
li{{background:#fff;border-radius:9px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);
display:flex;justify-content:space-between;align-items:center}}
li a{{flex:1;padding:15px 16px;color:#29435c;font-weight:700;text-decoration:none;font-size:15px}}
.n{{padding-right:16px;font-size:12px;color:#8a8f96}}
</style></head><body><div class="wrap"><h1>實價登錄銷售矩陣</h1><ul>
{items}
</ul></div></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
