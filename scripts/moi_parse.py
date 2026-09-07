"""
把內政部開放資料的預售屋 CSV 轉成本專案用的紀錄格式。

開放資料與實價登錄網站上「匯出 Excel」的欄位不同：
  - 面積是平方公尺，價格是元（網站匯出的是坪與萬元）
  - CSV 有兩列表頭（第一列中文、第二列英文），要略過第二列
  - 主檔之外還有 _build / _land / _park 三個子檔，用「編號」關聯

每個縣市每種交易各一個檔，命名規則 {縣市代碼}_lvr_land_{類別}.csv，
類別 a=成屋買賣、b=預售屋、c=租賃。所以台中預售屋是 b_lvr_land_b.csv。
"""

from __future__ import annotations

import csv
import io
import re
import zipfile

PING_PER_M2 = 0.3025
WAN = 10000.0

CH_NUM = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
    "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
    "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
    "二十一": 21, "二十二": 22, "二十三": 23, "二十四": 24, "二十五": 25,
}


def _num(value) -> float:
    """把 '1,234.5' / '1234元' / '' 這類字串轉成 float，失敗回 0。"""
    if value is None:
        return 0.0
    s = str(value).strip().replace(",", "")
    s = re.sub(r"[^\d.\-]", "", s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def m2_to_ping(v) -> float:
    return round(_num(v) * PING_PER_M2, 2)


def yuan_to_wan(v) -> float:
    return round(_num(v) / WAN, 1)


def ch_floor(text) -> int | None:
    """'四層' -> 4；'地下一層' -> -1；認不出來回 None。"""
    if not text:
        return None
    s = str(text).strip()
    sign = -1 if s.startswith("地下") else 1
    s = s.replace("地下", "").replace("層", "").strip()
    if s.isdigit():
        return sign * int(s)
    return sign * CH_NUM[s] if s in CH_NUM else None


def split_unit(dong_hao: str) -> tuple[str, int | None]:
    """
    從「棟及號」拆出欄位代號與樓層。實價登錄這欄的寫法不只一種：
      'B棟05F-05號'  -> ('B05', 5)     棟別+樓層+戶號
      'B7棟0號'      -> ('B7',  None)  只有棟別，樓層要另外從移轉層次取
      '店9棟0號'     -> ('店9', None)
    """
    s = (dong_hao or "").strip()
    m = re.match(r"^([A-Za-z\u4e00-\u9fff]+?)棟0?(\d+)F-0?(\d+)號", s)
    if m:
        return f"{m.group(1)}{int(m.group(3)):02d}", int(m.group(2))
    m = re.match(r"^(.+?)棟", s)
    if m:
        return m.group(1).strip(), None
    return s or "未標示", None


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict]:
    """讀出 ZIP 內一個 CSV，略過第二列的英文表頭。"""
    try:
        raw = zf.read(name)
    except KeyError:
        return []
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return []
    header = [h.strip() for h in rows[0]]
    body = rows[1:]
    # 第二列若是英文表頭就丟掉
    if body and body[0] and re.match(r"^[a-zA-Z_ ]+$", body[0][0].strip() or "x"):
        body = body[1:]
    out = []
    for r in body:
        if not any(c.strip() for c in r):
            continue
        out.append({header[i]: (r[i] if i < len(r) else "") for i in range(len(header))})
    return out


def _pick(row: dict, *needles: str) -> str:
    """依關鍵字模糊找欄位，因為表頭用字偶爾會微調。"""
    for needle in needles:
        for k, v in row.items():
            if needle in k:
                return v
    return ""


def presale_filenames(county: str) -> dict[str, str]:
    c = county.lower()
    return {
        "main": f"{c}_lvr_land_b.csv",
        "build": f"{c}_lvr_land_b_build.csv",
        "park": f"{c}_lvr_land_b_park.csv",
    }


def extract(zf: zipfile.ZipFile, county: str, project_name: str) -> list[dict]:
    """從一個 ZIP 撈出指定建案的所有預售屋登錄，轉成正規化紀錄。"""
    names = presale_filenames(county)
    present = set(zf.namelist())
    if names["main"] not in present:
        return []

    main = _read_csv(zf, names["main"])
    parks = _read_csv(zf, names["park"])
    builds = _read_csv(zf, names["build"])

    park_by_id: dict[str, list[dict]] = {}
    for p in parks:
        pid = _pick(p, "編號").strip()
        base = pid.split("-")[0] if "-" in pid else pid
        park_by_id.setdefault(base, []).append(p)

    build_by_id: dict[str, list[dict]] = {}
    for b in builds:
        bid = _pick(b, "編號").strip()
        base = bid.split("-")[0] if "-" in bid else bid
        build_by_id.setdefault(base, []).append(b)

    records = []
    for row in main:
        if _pick(row, "建案名稱").strip() != project_name:
            continue

        rid = _pick(row, "編號").strip()
        dong_hao = _pick(row, "棟及號").strip()
        unit, floor = split_unit(dong_hao)
        if floor is None:
            floor = ch_floor(_pick(row, "移轉層次"))
        if floor is None:
            for b in build_by_id.get(rid, []):
                floor = ch_floor(_pick(b, "建物分層", "分層"))
                if floor is not None:
                    break
        if floor is None:
            floor = 0

        total_price = yuan_to_wan(_pick(row, "總價元", "總價"))
        b_area_m2 = _num(_pick(row, "建物移轉總面積"))
        p_area_m2 = _num(_pick(row, "車位移轉總面積"))
        park_price = yuan_to_wan(_pick(row, "車位總價元", "車位總價"))

        parking = []
        for p in park_by_id.get(rid, []):
            parking.append({
                "type": _pick(p, "車位類別").strip() or "車位",
                "area": m2_to_ping(_pick(p, "車位移轉面積", "車位面積", "面積")),
                "price": yuan_to_wan(_pick(p, "車位價格", "價格")),
            })
        if parking and not park_price:
            park_price = round(sum(p["price"] for p in parking), 1)

        total_area = round((b_area_m2 + p_area_m2) * PING_PER_M2, 2)
        building_area = round(b_area_m2 * PING_PER_M2, 2)
        building_price = round(total_price - park_price, 1)

        rooms = _pick(row, "格局-房", "現況格局-房")
        halls = _pick(row, "格局-廳", "現況格局-廳")
        baths = _pick(row, "格局-衛", "現況格局-衛")
        if any(_num(x) for x in (rooms, halls, baths)):
            layout = f"{int(_num(rooms))}房{int(_num(halls))}廳{int(_num(baths))}衛"
        else:
            layout = _pick(row, "主要用途").strip() or "未標示"

        raw_date = _pick(row, "交易年月日").strip()
        cancel = _pick(row, "解約情形").strip()

        records.append({
            "unit": unit,
            "floor": floor,
            "dong_hao": dong_hao,
            "date": _fmt_ym(raw_date),
            "full_date": _fmt_date(raw_date),
            "raw_date": raw_date,
            "total_price": total_price,
            "total_area": total_area,
            "unit_price": round(building_price / building_area, 2) if building_area else 0,
            "building_area": building_area,
            "building_price": building_price,
            "building_unit_price": round(building_price / building_area, 2) if building_area else 0,
            "parking": parking,
            "layout": layout,
            "address": _pick(row, "土地位置建物門牌", "門牌").strip(),
            "deal_type": _pick(row, "交易標的").strip(),
            "cancelled": bool(cancel),
            "cancel_date": _fmt_date(re.sub(r"\D", "", cancel)[:7]) if cancel else "",
            "key": f"{project_name}|{dong_hao}|{raw_date}|{int(total_price)}",
        })
    return records


def _fmt_date(roc: str) -> str:
    d = re.sub(r"\D", "", roc or "")
    if len(d) == 7:
        return f"{d[:3]}-{d[3:5]}-{d[5:7]}"
    if len(d) == 6:
        return f"{d[:2]}-{d[2:4]}-{d[4:6]}"
    return roc or ""


def _fmt_ym(roc: str) -> str:
    d = re.sub(r"\D", "", roc or "")
    return f"{d[:3]}-{d[3:5]}" if len(d) >= 5 else (roc or "")
