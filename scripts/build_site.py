"""
把正規化後的紀錄產成互動版矩陣網頁。

刻意不使用 JavaScript：詳情面板用隱藏 radio + label + CSS :checked 切換。
這樣在會擋掉 JS 的環境（iOS 檔案 App 的 QuickLook 預覽、部分雲端硬碟預覽）
一樣點得動。所有 id 只用 ASCII，中文只出現在顯示文字裡。
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

TPE = timezone(timedelta(hours=8))


def slug(unit: str) -> str:
    """欄位代號轉成 ASCII id：店1 -> S1，其他非 ASCII 字元轉成碼點。"""
    s = unit.replace("店", "S")
    return re.sub(r"[^A-Za-z0-9]", lambda m: f"u{ord(m.group()):x}", s)


def fw(n: float) -> str:
    return f"{n:,.0f}" if float(n).is_integer() else f"{n:,.1f}"


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def build(project: dict, records: list[dict]) -> str:
    if not records:
        return _empty_page(project)

    by_key = {}
    for r in records:
        # 同一戶同一樓層若有多筆（少見，通常是解約後重賣），留最新的一筆
        k = f"{slug(r['unit'])}_{r['floor']}"
        prev = by_key.get(k)
        if prev is None or r["raw_date"] > prev["raw_date"]:
            by_key[k] = r

    keys = list(by_key.keys())
    shops = sorted({r["unit"] for r in by_key.values() if r["unit"].startswith("店")})
    homes = sorted({r["unit"] for r in by_key.values() if not r["unit"].startswith("店")})

    home_floors = sorted({r["floor"] for r in by_key.values()
                          if not r["unit"].startswith("店")}, reverse=True)
    if home_floors:
        floors = list(range(max(home_floors), min(min(home_floors), 2) - 1, -1))
        floors = [f for f in floors if f >= 2] or home_floors
    else:
        floors = []

    def meta(unit):
        rs = [r for r in by_key.values() if r["unit"] == unit]
        lay = sorted({r["layout"] for r in rs})
        ar = sorted({r["building_area"] for r in rs})
        return (lay[0] if len(lay) == 1 else " / ".join(lay),
                f"{ar[0]:.1f}" if len(ar) == 1 else f"{min(ar):.1f}~{max(ar):.1f}")

    def cell(unit, floor):
        k = f"{slug(unit)}_{floor}"
        r = by_key.get(k)
        if not r:
            return '<td class="empty"><span class="empty-label">尚未登錄</span></td>'
        cls = "sold cancelled" if r["cancelled"] else "sold"
        badge = '<div class="cancel-badge">已解約</div>' if r["cancelled"] else ""
        return (f'<td class="{cls}" id="cell-{k}"><label for="r-{k}">'
                f'<div class="date">{_esc(r["date"])}</div>'
                f'<div class="unit-price">{r["unit_price"]:.1f} <span class="unit">萬/坪</span></div>'
                f'<div class="total-price">{r["total_price"]:,.0f}萬元</div>{badge}</label></td>')

    def matrix(units, rows, klass, corner, show_layout):
        head = "".join(f'<th id="colhead-{slug(u)}">{_esc(u)}</th>' for u in units)
        layout_row = ""
        if show_layout:
            layout_row = ('<tr class="meta-row"><td class="corner-label">格局</td>'
                          + "".join(f'<td class="meta">{_esc(meta(u)[0])}</td>' for u in units)
                          + "</tr>")
        area_row = ('<tr class="meta-row"><td class="corner-label">建物面積</td>'
                    + "".join(f'<td class="meta">{meta(u)[1]} 坪</td>' for u in units) + "</tr>")
        body = ""
        for f in rows:
            body += (f'<tr><td class="floor" id="floorlabel-{f}">{f}F</td>'
                     + "".join(cell(u, f) for u in units) + "</tr>\n")
        cols = "".join("<col>" for _ in units)
        return f'''<div class="grid-wrap">
<table class="matrix {klass}">
<colgroup><col style="width:58px">{cols}</colgroup>
<thead><tr class="unit-row"><th>{corner}</th>{head}</tr>{layout_row}{area_row}</thead>
<tbody>
{body}</tbody></table></div>'''

    sections = ""
    if homes:
        sections += '<h3 class="section">住宅戶<span class="hint">點格子看明細</span></h3>'
        sections += matrix(homes, floors, "res", "戶別 ／ 樓層", True)
    if shops:
        sections += '<h3 class="section">店面</h3>'
        shop_floors = sorted({r["floor"] for r in by_key.values()
                              if r["unit"].startswith("店")}, reverse=True)
        sections += matrix(shops, shop_floors, "shop", "店別 ／ 樓層", False)

    panels = "\n".join(_panel(k, by_key[k]) for k in keys)
    radios = ('<input type="radio" name="cellsel" id="r-none" class="cellsel" checked>\n'
              + "\n".join(f'<input type="radio" name="cellsel" id="r-{k}" class="cellsel">'
                          for k in keys))

    rules = []
    for k in keys:
        r = by_key[k]
        rules.append(f"#r-{k}:checked ~ .layout .panels #p-{k}{{display:block}}")
        rules.append(f"#r-{k}:checked ~ .layout #cell-{k}"
                     "{box-shadow:inset 0 0 0 2px #3d6fb0;background:#fbe6c8}")
        if r["cancelled"]:
            rules.append(f"#r-{k}:checked ~ .layout #cell-{k}{{background:#e6e6e6}}")
        rules.append(f"#r-{k}:checked ~ .layout #colhead-{slug(r['unit'])}"
                     "{background:#90b6df;color:#0d2c4d}")
        rules.append(f"#r-{k}:checked ~ .layout #floorlabel-{r['floor']}"
                     "{background:#90b6df;color:#0d2c4d}")
    rules.append(",".join(f"#r-{k}:checked ~ .layout .panels" for k in keys)
                 + "{pointer-events:auto}")

    live = [r for r in by_key.values() if not r["cancelled"]]
    n_cancel = sum(1 for r in by_key.values() if r["cancelled"])
    price_note = ""
    if live:
        lo = min(r["unit_price"] for r in live)
        hi = max(r["unit_price"] for r in live)
        price_note = f'<div class="stat"><div class="k">有效交易單價</div><div class="v">{lo:.1f}~{hi:.1f} <span class="su">萬/坪</span></div></div>'

    alert = ""
    if n_cancel:
        pct = n_cancel / len(by_key) * 100
        alert = (f'<div class="alert"><strong>{len(by_key)} 筆登錄中有 {n_cancel} 筆事後解約'
                 f'（{pct:.0f}%）。</strong>解約價不代表實際成交行情，看行情時請以未解約的紀錄為準。</div>')

    dates = sorted(r["date"] for r in by_key.values())
    span = f"{dates[0]} ～ {dates[-1]}" if dates else ""
    updated = datetime.now(TPE).strftime("%Y-%m-%d %H:%M")

    return _PAGE.format(
        title=_esc(project.get("title", project["name"])),
        subtitle=_esc(project.get("subtitle", "")),
        span=_esc(span),
        updated=updated,
        n_total=len(by_key),
        n_cancel=n_cancel,
        price_note=price_note,
        alert=alert,
        radios=radios,
        sections=sections,
        panels=panels,
        rules="\n".join(rules),
    )


def _panel(key: str, r: dict) -> str:
    parking = "".join(
        f'<tr><td>{_esc(p["type"])}</td><td>{p["area"]:.1f}坪</td>'
        f'<td>{(p["price"]/p["area"] if p["area"] else 0):.1f}萬</td>'
        f'<td>{fw(p["price"])}萬</td></tr>' for p in r["parking"])
    tag_cancel = '<span class="tag tag-cancel">已解約</span>' if r["cancelled"] else ""
    note = (f'<div class="cancel-note">本筆交易已於 {_esc(r["cancel_date"])} 解約</div>'
            if r["cancelled"] and r["cancel_date"] else "")
    name = (f'{_esc(r["unit"])}　1F' if r["unit"].startswith("店")
            else f'{_esc(r["unit"])}戶　{r["floor"]}F')
    return f'''<div class="detail-panel" id="p-{key}">
<div class="detail-header"><label class="collapse-btn" for="r-none">✕ 關閉</label><h2>登錄詳情</h2></div>
<div class="which">{name}</div>
<div class="address-box">{_esc(r["address"])}</div>
<div class="tags"><span class="tag">{_esc(r["layout"])}</span><span class="tag">{_esc(r["full_date"])} 成交</span>{tag_cancel}</div>
{note}
<div class="price-row">
<div class="price-item"><div class="big">{r["unit_price"]:.1f}<span class="u"> 萬/坪</span></div></div>
<div class="price-item mid"><div class="big">{r["total_area"]:.1f}<span class="u"> 坪</span></div></div>
<div class="price-item"><div class="big">{fw(r["total_price"])}<span class="u"> 萬</span></div></div>
</div>
<p class="comp-title">價格構成</p>
<table class="comp-table">
<thead><tr><th>類別</th><th>坪數</th><th>單價</th><th>總價</th></tr></thead>
<tbody>
<tr><td>建物面積</td><td>{r["building_area"]:.1f}坪</td><td>{r["building_unit_price"]:.1f}萬</td><td>{fw(r["building_price"])}萬</td></tr>
{parking}
<tr class="total-row"><td>合計</td><td></td><td></td><td>{fw(r["total_price"])}萬</td></tr>
</tbody></table>
<p class="deal-type">交易標的：{_esc(r["deal_type"])}</p>
</div>'''


def _empty_page(project: dict) -> str:
    updated = datetime.now(TPE).strftime("%Y-%m-%d %H:%M")
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(project.get('title', project['name']))}</title>
<style>body{{font-family:"Noto Sans TC","PingFang TC",sans-serif;background:#f4f5f7;
padding:40px 20px;color:#4a5b6e}}.box{{max-width:520px;margin:0 auto;background:#fff;
border-radius:10px;padding:24px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}</style></head>
<body><div class="box"><h1 style="font-size:18px;color:#1f2d3d">{_esc(project.get('title', project['name']))}</h1>
<p>目前查到的登錄筆數為 0。可能是這個區間內沒有新登錄，或建案名稱與實價登錄上的寫法不一致
（需完全相符）。</p><p style="font-size:12px;color:#8a8f96">最後檢查：{updated}</p></div></body></html>"""


_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}　實價登錄銷售矩陣</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:"Noto Sans TC","PingFang TC","Microsoft JhengHei",Arial,sans-serif;
background:#f4f5f7;margin:0;padding:28px 18px;color:#333}}
.wrap{{max-width:1200px;margin:0 auto}}
h1{{font-size:20px;font-weight:700;color:#1f2d3d;margin:0 0 4px}}
.subtitle{{font-size:13px;color:#7a7f87;margin:0 0 16px;line-height:1.6}}
h3.section{{font-size:15px;color:#1f2d3d;margin:24px 0 8px;font-weight:700}}
h3.section .hint{{font-weight:400;font-size:12px;color:#8a8f96;margin-left:6px}}
.stats{{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}}
.stat{{background:#fff;border-radius:8px;padding:10px 14px;box-shadow:0 1px 3px rgba(0,0,0,.07);flex:1;min-width:128px}}
.stat .k{{font-size:11px;color:#8a8f96}}
.stat .v{{font-size:18px;font-weight:700;color:#29435c;margin-top:2px}}
.stat .su{{font-size:11px;font-weight:400}}
.stat.warn .v{{color:#b23b3b}}
.alert{{background:#fdf0ef;border-left:4px solid #d9584f;border-radius:6px;padding:11px 14px;
font-size:12.5px;color:#7a3330;line-height:1.65;margin-bottom:18px}}
.cellsel{{position:absolute;opacity:0;width:1px;height:1px;pointer-events:none}}
.layout{{display:flex;align-items:flex-start;gap:20px}}
.grids{{flex:1;min-width:0}}
.grid-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table.matrix{{width:100%;border-collapse:collapse;background:#fff;box-shadow:0 1px 4px rgba(0,0,0,.08);table-layout:fixed}}
table.res{{min-width:460px}}table.shop{{min-width:620px}}
table.matrix th,table.matrix td{{border:1px solid #e3e6ea;text-align:center;padding:6px 4px;vertical-align:middle}}
thead tr.unit-row th{{background:#dce6f2;color:#29435c;font-size:14px;font-weight:700;padding:10px 4px;transition:background .15s,color .15s}}
tr.meta-row td{{background:#eef3f9;color:#4a5b6e;font-size:11.5px;font-weight:500}}
tr.meta-row td.corner-label{{background:#dce6f2;color:#29435c;font-weight:700;font-size:12.5px}}
td.floor{{background:#f7f8fa;color:#2c3a4a;font-weight:700;font-size:14px;transition:background .15s,color .15s}}
td.empty{{background:#fbfbfb}}
.empty-label{{color:#b7bbc2;font-size:12px}}
td.sold{{background:#fdf1e4;padding:0;transition:box-shadow .15s}}
td.sold label{{display:block;padding:8px 4px;cursor:pointer;-webkit-tap-highlight-color:rgba(61,111,176,.25)}}
td.sold:hover{{box-shadow:inset 0 0 0 1px #9db8d6}}
td.sold:active{{box-shadow:inset 0 0 0 2px #3d6fb0}}
.date{{font-size:11px;color:#8a8f96;margin-bottom:2px}}
.unit-price{{font-size:15px;font-weight:700;color:#d9481f;line-height:1.2}}
.unit-price .unit{{font-size:10px;font-weight:500}}
.total-price{{font-size:11px;color:#8a8f96;margin-top:2px}}
td.cancelled{{background:#f1f1f1}}
td.cancelled .unit-price{{color:#a3a3a3;text-decoration:line-through}}
td.cancelled .total-price{{text-decoration:line-through}}
.cancel-badge{{margin-top:2px;font-size:10px;color:#b23b3b;font-weight:700}}
.panels{{width:330px;flex-shrink:0;pointer-events:none}}
.detail-panel{{display:none;background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);padding:16px 18px}}
.detail-header{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.collapse-btn{{color:#3d6fb0;font-size:13px;cursor:pointer;padding:6px 10px;margin:-6px -4px;border-radius:5px;background:#eef3f9;user-select:none}}
.detail-header h2{{font-size:16px;font-weight:700;margin:0;color:#1f2d3d}}
.which{{font-size:14px;font-weight:700;color:#29435c;margin-bottom:8px}}
.address-box{{background:#f7f8fa;border-radius:8px;padding:11px 13px;font-size:13.5px;color:#29435c;line-height:1.5;margin-bottom:10px}}
.tags{{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap}}
.tag{{background:#e6eef8;color:#29435c;font-size:12px;font-weight:600;padding:4px 10px;border-radius:5px}}
.tag.tag-cancel{{background:#fbe6e6;color:#a3312f}}
.cancel-note{{background:#fdf0ef;border-radius:6px;padding:8px 11px;font-size:12px;color:#a3312f;margin-bottom:12px}}
.price-row{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px}}
.price-item{{text-align:center;flex:1}}
.price-item .big{{font-size:19px;font-weight:700;color:#d9481f}}
.price-item .big .u{{font-size:11px}}
.price-item.mid .big{{color:#29435c}}
.comp-title{{font-size:13px;font-weight:700;color:#1f2d3d;margin:0 0 6px}}
table.comp-table{{width:100%;border-collapse:collapse}}
table.comp-table th{{color:#8a8f96;font-size:12px;font-weight:500;border:none;border-bottom:1px solid #e3e6ea;padding:6px 2px;text-align:right}}
table.comp-table th:first-child{{text-align:left}}
table.comp-table td{{border:none;border-bottom:1px solid #f0f1f3;font-size:13px;padding:7px 2px;text-align:right;color:#2c3a4a}}
table.comp-table td:first-child{{text-align:left}}
table.comp-table tr.total-row td{{font-weight:700;color:#d9481f;border-bottom:none;padding-top:9px}}
.deal-type{{font-size:11.5px;color:#8a8f96;margin:10px 0 0}}
.footnote{{margin-top:16px;font-size:12px;color:#8a8f96;line-height:1.7}}
{rules}
@media (max-width:760px){{
body{{padding:16px 10px 300px}}
h1{{font-size:17px}}.subtitle{{font-size:11.5px}}
h3.section{{font-size:13.5px;margin:20px 0 7px}}
.stat{{padding:8px 11px;min-width:46%}}.stat .v{{font-size:16px}}
.alert{{font-size:11.5px;padding:10px 12px}}
.layout{{flex-direction:column;gap:16px}}
table.res{{min-width:380px}}table.shop{{min-width:560px}}
table.matrix th,table.matrix td{{padding:4px 2px}}
thead tr.unit-row th{{font-size:11.5px;padding:7px 2px}}
tr.meta-row td{{font-size:9.5px;padding:5px 2px}}
tr.meta-row td.corner-label{{font-size:10px}}
td.floor{{font-size:12px}}
td.sold label{{padding:6px 2px}}
.date{{font-size:9px}}.unit-price{{font-size:12px}}.unit-price .unit{{font-size:8px}}
.total-price{{font-size:9px}}.cancel-badge{{font-size:8px}}
.panels{{position:fixed;left:0;right:0;bottom:0;width:100%;z-index:50;padding:0 8px 8px}}
.detail-panel{{max-height:74vh;overflow-y:auto;-webkit-overflow-scrolling:touch;
border-radius:12px 12px 0 0;padding:14px 14px 18px;box-shadow:0 -3px 16px rgba(0,0,0,.18)}}
.price-item .big{{font-size:17px}}
.collapse-btn{{padding:8px 12px;font-size:14px}}
}}
</style>
</head>
<body>
<div class="wrap">
<h1>{title}　實價登錄銷售矩陣</h1>
<p class="subtitle">{subtitle}　資料來源：內政部不動產交易實價查詢服務網　登錄區間：{span}</p>
<div class="stats">
<div class="stat"><div class="k">登錄筆數</div><div class="v">{n_total} 筆</div></div>
<div class="stat warn"><div class="k">其中已解約</div><div class="v">{n_cancel} 筆</div></div>
{price_note}
<div class="stat"><div class="k">最後更新</div><div class="v" style="font-size:14px">{updated}</div></div>
</div>
{alert}
{radios}
<div class="layout">
<div class="grids">
{sections}
</div>
<div class="panels">
{panels}
</div>
</div>
<p class="footnote">
每格由上至下：交易月份（民國年-月）／單價（萬元・坪）／總價（萬元）。「尚未登錄」表示該樓層戶別尚無實價登錄紀錄，不等於未銷售。<br>
單價與「建物面積」皆已扣除車位；詳情面板中的「總面積」則含車位坪數，兩者不同屬正常。<br>
本頁由排程自動更新，資料以內政部實價查詢服務網為準。
</p>
</div>
</body>
</html>
"""
