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
    args = ap.parse_args()

    config = json.loads((ROOT / "projects.json").read_text(encoding="utf-8"))
    projects = config["projects"]

    n_seasons = config.get("backfill_seasons", 8) if args.backfill else 1
    seasons = moi_fetch.recent_seasons(n_seasons)

    # 先把要用的 ZIP 抓下來，多個建案共用，避免重複下載
    zips = []
    current = moi_fetch.fetch_current()
    if current:
        zips.append(("current", current))
    for s in seasons:
        z = moi_fetch.fetch_season(s)
        if z:
            zips.append((s, z))

    if not zips:
        print("沒有抓到任何資料來源，中止（保留現有頁面不動）。")
        return 1

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

        if not store:
            print(f"  [{slug}] 查無資料，跳過寫檔以免覆蓋掉先前的頁面")
            continue

        save_store(slug, store)
        page = build_site.build(proj, list(store.values()))
        (DOCS / f"{slug}.html").write_text(page, encoding="utf-8")
        index_rows.append((proj, len(store)))

    if index_rows:
        (DOCS / "index.html").write_text(_index(index_rows), encoding="utf-8")

    return 1 if failed and not index_rows else 0


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
