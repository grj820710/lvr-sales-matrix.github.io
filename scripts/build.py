"""
掃描 sources/ 底下的銷售表，逐一產出互動版矩陣網頁到 docs/。

流程很單純：有什麼檔案就產什麼頁面。沒有下載、沒有跨次累積——
匯出檔本身就是完整快照，所以重跑一次的結果必然與網站一致。

用法：
    python scripts/build.py
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import build_site
import parse_xls
import tongyong

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "sources"
DOCS = ROOT / "docs"
DATA = ROOT / "data"

SUFFIXES = (".xls", ".xlsx")


def load_config() -> dict:
    path = ROOT / "projects.json"
    if not path.exists():
        return {}
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return {p["name"]: p for p in cfg.get("projects", [])}


def make_slug(name: str, stem: str) -> str:
    """網址用的 ASCII 代號，一律取自檔名。

    純英數檔名沿用原樣（連字號保留）；含中文的檔名轉成通用拼音，
    不帶聲調、不含空白，例如「勝興豐川」→ shengsingfongchuan。
    真的轉不出來（例如檔名全是符號）才退回雜湊值。
    """
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in stem)
    if has_cjk:
        slug = tongyong.romanize(stem)
        if slug:
            return slug
    else:
        ascii_stem = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-").lower()
        if ascii_stem:
            return ascii_stem
    return "p-" + hashlib.md5(name.encode("utf-8")).hexdigest()[:8]


def main() -> int:
    if not SOURCES.exists():
        print(f"找不到 {SOURCES}／請建立 sources 資料夾並放入銷售表。")
        return 1

    files = sorted(f for f in SOURCES.iterdir()
                   if f.suffix.lower() in SUFFIXES and not f.name.startswith("~$"))
    if not files:
        print(f"sources/ 底下沒有 {'／'.join(SUFFIXES)} 檔案，沒有東西可以產。")
        return 1

    config = load_config()
    DOCS.mkdir(exist_ok=True)
    DATA.mkdir(exist_ok=True)
    (DOCS / ".nojekyll").touch()

    built = []
    failed = False

    for f in files:
        print(f"\n處理 {f.name}")
        try:
            name, records = parse_xls.parse(f)
        except Exception as exc:  # noqa: BLE001
            print(f"  解析失敗：{exc}")
            failed = True
            continue

        if not records:
            print("  檔案裡沒有任何交易紀錄，略過")
            failed = True
            continue

        meta = config.get(name, {})
        slug = meta.get("slug") or make_slug(name, f.stem)

        n_cancel = sum(1 for r in records if r["cancelled"])
        print(f"  建案：{name}　共 {len(records)} 筆，其中解約 {n_cancel} 筆")
        for r in sorted(records, key=lambda x: (x["unit"], -x["floor"], x["raw_date"])):
            flag = " [解約]" if r["cancelled"] else ""
            print(f"    {r['unit']:>6} {r['floor']:>3}F  {r['full_date']}  "
                  f"{r['total_price']:>8,.0f}萬  {r['unit_price']:>6.2f}萬/坪{flag}")

        project = {
            "name": name,
            "title": meta.get("title", name),
            "subtitle": meta.get("subtitle", records[0]["address"]),
        }
        (DOCS / f"{slug}.html").write_text(
            build_site.build(project, records), encoding="utf-8")
        (DATA / f"{slug}.json").write_text(
            json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  → docs/{slug}.html")
        built.append((project, slug, len(records), n_cancel))

    if built:
        (DOCS / "index.html").write_text(_index(built), encoding="utf-8")

    # 清掉已經沒有對應來源檔的產出。只有在全部來源都處理成功時才做，
    # 否則一次解析失敗就會把還在用的頁面刪掉。
    if failed:
        print("\n有來源處理失敗，略過清理步驟以免誤刪既有頁面")
    else:
        _cleanup({slug for _, slug, _, _ in built})

    if built:
        print(f"\n完成，共 {len(built)} 個建案")

    return 1 if failed else 0


def _cleanup(keep: set[str]) -> None:
    """刪除不再對應任何來源檔的頁面與資料。"""
    removed = []
    for f in sorted(DOCS.glob("*.html")):
        if f.name == "index.html":
            continue
        if f.stem not in keep:
            f.unlink()
            removed.append(f"docs/{f.name}")
    for f in sorted(DATA.glob("*.json")):
        if f.stem not in keep:
            f.unlink()
            removed.append(f"data/{f.name}")
    if removed:
        print("\n已移除沒有對應來源檔的產出：")
        for r in removed:
            print(f"  - {r}")


def _index(rows) -> str:
    items = "\n".join(
        f'<li><a href="{slug}.html">{proj["title"]}</a>'
        f'<span class="n">{n} 筆'
        + (f'　解約 {nc}' if nc else "")
        + "</span></li>"
        for proj, slug, n, nc in rows)
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
.n{{padding-right:16px;font-size:12px;color:#8a8f96;white-space:nowrap}}
</style></head><body><div class="wrap"><h1>實價登錄銷售矩陣</h1><ul>
{items}
</ul></div></body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
