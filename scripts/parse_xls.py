"""
解析從「不動產交易實價查詢服務網」匯出的銷售表（.xls / .xlsx）。

匯出檔有四張工作表：案件列表、土地、建物、車位，以「編號」關聯。
與開放資料批次檔不同，這裡的面積已是坪、金額已是萬元，且解約狀態是最新的
——這正是改用匯出檔的原因：筆數與網站上看到的完全一致，沒有發布空窗。

「棟及號」的寫法不只一種，兩種都要吃：
    'B棟05F-05號'  棟別 + 樓層 + 戶號  → 欄位 B05，樓層 5
    'B7棟0號'      只有棟別            → 欄位 B7，樓層改從「樓別/樓高」取
    '店9棟0號'     店面                → 欄位 店9
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SHEET_MAIN = "案件列表"
SHEET_PARK = "車位"


def _num(v) -> float:
    if v is None:
        return 0.0
    s = re.sub(r"[^\d.\-]", "", str(v).replace(",", ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _txt(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan", "nat", "none") else s


def split_unit(dong_hao: str) -> tuple[str, str, int | None]:
    """從「棟及號」拆出 (欄位代號, 顯示標籤, 樓層)。

    實價登錄這一欄的寫法各案不同，目前遇過三種：

        'B棟05F-05號'  棟別 + 樓層 + 戶號   → B05 / B棟05號 / 5 樓
        'A棟1號'       棟別 + 戶號          → A01 / A棟1號  / 樓層另取
        'B7棟0號'      只有棟別（戶號為 0） → B7  / B7棟    / 樓層另取

    第二種是重點：戶號在「號」的位置。若只取「棟」前面那段，A棟1號到
    A棟6號會全部併成同一欄，整張矩陣就失去辨識度。
    """
    s = _txt(dong_hao)

    # 形式一：棟 + 樓層 + 戶號
    m = re.match(r"^(.+?)棟0*(\d+)F-0*(\d+)號", s)
    if m:
        tower, floor, no = m.group(1).strip(), int(m.group(2)), int(m.group(3))
        return f"{tower}{no:02d}", f"{tower}棟{no:02d}號", floor

    # 形式二／三：棟 + 號（號為 0 代表未編戶號）
    m = re.match(r"^(.+?)棟0*(\d+)號$", s)
    if m:
        tower, no = m.group(1).strip(), int(m.group(2))
        if no:
            return f"{tower}{no:02d}", f"{tower}棟{no}號", None
        return tower, f"{tower}棟", None

    # 其他寫法：整串當一欄，標籤保留原文以免誤導
    m = re.match(r"^(.+?)棟", s)
    tower = m.group(1).strip() if m else (s or "未標示")
    return tower, s or "未標示", None


def _fmt_date(roc) -> str:
    d = re.sub(r"\D", "", _txt(roc))
    if len(d) == 7:
        return f"{d[:3]}-{d[3:5]}-{d[5:7]}"
    if len(d) == 6:
        return f"{d[:2]}-{d[2:4]}-{d[4:6]}"
    return _txt(roc)


def parse(path: Path) -> tuple[str, list[dict]]:
    """回傳 (建案名稱, 紀錄清單)。"""
    xl = pd.ExcelFile(path)
    if SHEET_MAIN not in xl.sheet_names:
        raise ValueError(
            f"{path.name}：找不到「{SHEET_MAIN}」工作表，實際有 {xl.sheet_names}。"
            f"請確認這是實價登錄網站匯出的銷售表。")

    main = pd.read_excel(xl, sheet_name=SHEET_MAIN, skiprows=1)
    main.columns = [str(c).strip() for c in main.columns]

    park = pd.DataFrame()
    if SHEET_PARK in xl.sheet_names:
        park = pd.read_excel(xl, sheet_name=SHEET_PARK, header=0)
        park.columns = [str(c).strip() for c in park.columns]

    def col(df, *names):
        for n in names:
            for c in df.columns:
                if n in c:
                    return c
        return None

    c_id     = col(main, "編號")
    c_addr   = col(main, "建物坐落", "坐落")
    c_dong   = col(main, "棟及號")
    c_proj   = col(main, "建案名稱")
    c_date   = col(main, "交易日期")
    c_total  = col(main, "總價")
    c_unitp  = col(main, "單價")
    c_area   = col(main, "總面積")
    c_floor  = col(main, "樓別")
    c_layout = col(main, "建物格局")
    c_parkp  = col(main, "車位總價")
    c_cancel = col(main, "解約")
    c_deal   = col(main, "交易標的")

    missing = [n for n, c in [("編號", c_id), ("棟及號", c_dong),
                              ("交易日期", c_date), ("總價", c_total),
                              ("總面積", c_area)] if c is None]
    if missing:
        raise ValueError(f"{path.name}：缺少必要欄位 {missing}，"
                         f"實際欄位為 {list(main.columns)}")

    p_id   = col(park, "序號", "編號") if len(park) else None
    p_type = col(park, "車位類別", "類別") if len(park) else None
    p_price= col(park, "車位價格", "價格") if len(park) else None
    p_area = col(park, "車位面積", "面積") if len(park) else None

    project = ""
    records = []
    for _, r in main.iterrows():
        rid = _txt(r[c_id])
        if not rid:
            continue
        if c_proj and not project:
            project = _txt(r[c_proj])

        unit, unit_label, floor = split_unit(r[c_dong])
        if floor is None and c_floor:
            fl = _txt(r[c_floor]).split("/")[0]
            floor = int(_num(fl)) if fl else None
        if floor is None:
            floor = 0

        total_price = _num(r[c_total])
        total_area = _num(r[c_area])

        parking = []
        if len(park) and p_id:
            base = rid.split("-")[0]
            hit = park[park[p_id].astype(str).str.match(rf"^{re.escape(base)}-\d+$")]
            for _, sp in hit.iterrows():
                price = _num(sp[p_price]) if p_price else 0.0
                # 車位工作表的價格是「元」，主表的車位總價是「萬元」
                if price > 10000:
                    price = round(price / 10000, 1)
                parking.append({
                    "type": _txt(sp[p_type]) if p_type else "車位",
                    "area": _num(sp[p_area]) if p_area else 0.0,
                    "price": price,
                })

        park_price = round(sum(p["price"] for p in parking), 1)
        if not park_price and c_parkp:
            park_price = _num(r[c_parkp])
        park_area = round(sum(p["area"] for p in parking), 2)

        building_area = round(total_area - park_area, 2)
        building_price = round(total_price - park_price, 1)
        b_unit = round(building_price / building_area, 2) if building_area else 0.0

        layout = _txt(r[c_layout]) if c_layout else ""
        if not layout:
            layout = "店面" if unit.startswith("店") else "未標示"

        cancel_raw = _txt(r[c_cancel]) if c_cancel else ""
        cancelled = bool(cancel_raw)

        raw_date = re.sub(r"\D", "", _txt(r[c_date]))
        records.append({
            "unit": unit,
            "unit_label": unit_label,
            "floor": int(floor),
            "dong_hao": _txt(r[c_dong]),
            "raw_date": raw_date,
            "date": f"{raw_date[:3]}-{raw_date[3:5]}" if len(raw_date) >= 5 else raw_date,
            "full_date": _fmt_date(raw_date),
            "total_price": total_price,
            "total_area": total_area,
            "unit_price": _num(r[c_unitp]) if c_unitp else b_unit,
            "building_area": building_area,
            "building_price": building_price,
            "building_unit_price": b_unit,
            "parking": parking,
            "layout": layout,
            "address": _txt(r[c_addr]) if c_addr else "",
            "deal_type": _txt(r[c_deal]) if c_deal else "",
            "cancelled": cancelled,
            "cancel_date": _fmt_date(cancel_raw) if cancelled else "",
            "key": f"{rid}|{_txt(r[c_dong])}|{raw_date}|{total_price:.0f}",
        })

    return project or path.stem, records
