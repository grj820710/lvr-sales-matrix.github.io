"""
從內政部「不動產成交案件實際資訊資料供應系統」下載開放資料 ZIP。

兩種來源：
  current  當期資料（每月 1/11/21 發布，只含最近十天左右的登錄）
  season   分季封存

重要：分季封存只免費提供最近幾季，較舊的季別官方會關閉免費下載。
此時網站不會回 404，而是把「系統簡介」那頁 HTML 原封不動吐回來。
所以下面判斷「開頭不是 PK」就當作該季別不提供，這是正常情況而非錯誤，
只印一行說明、不重試、也不讓整個流程失敗。
"""

from __future__ import annotations

import io
import time
import zipfile
from datetime import date

import requests

BASE = "https://plvr.land.moi.gov.tw"
# 參數順序照官方頁面實際送出的樣子（type 在 fileName 之前）
CURRENT_URL = f"{BASE}/Download?type=zip&fileName=lvr_landcsv.zip"
SEASON_URL = f"{BASE}/DownloadSeason?season={{season}}&type=zip&fileName=lvr_landcsv.zip"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Referer": f"{BASE}/DownloadOpenData",
    "Accept": "application/zip,application/octet-stream,*/*",
}

TIMEOUT = 180


class Result:
    """zf 有值代表成功；unavailable 代表對方回 HTML（該季別沒開放）。"""

    def __init__(self, zf=None, unavailable=False, error=None):
        self.zf = zf
        self.unavailable = unavailable
        self.error = error


def _get(url: str, retries: int = 3) -> Result:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.content
            if data[:2] == b"PK":
                return Result(zf=zipfile.ZipFile(io.BytesIO(data)))
            # 回了 HTML：該季別未開放免費下載，重試沒有意義
            return Result(unavailable=True)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            if attempt < retries:
                time.sleep(5 * attempt)
    return Result(error=last_err)


def fetch_current() -> Result:
    r = _get(CURRENT_URL)
    if r.zf:
        print("  當期資料：下載成功")
    elif r.unavailable:
        print("  當期資料：對方回傳網頁而非檔案，可能正在維護")
    else:
        print(f"  當期資料：下載失敗（{r.error}）")
    return r


def fetch_season(season: str) -> Result:
    r = _get(SEASON_URL.format(season=season))
    if r.zf:
        print(f"  {season}：下載成功")
    elif r.unavailable:
        print(f"  {season}：官方未開放此季別的免費下載，略過")
    else:
        print(f"  {season}：下載失敗（{r.error}）")
    return r


def recent_seasons(n: int, today: date | None = None) -> list[str]:
    """最近 n 個季別，新到舊。不含當季（當季還在「當期」裡，尚未封存）。"""
    today = today or date.today()
    roc_year = today.year - 1911
    quarter = (today.month - 1) // 3 + 1
    out = []
    for _ in range(n + 1):
        out.append(f"{roc_year}S{quarter}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            roc_year -= 1
    return out[1:]
