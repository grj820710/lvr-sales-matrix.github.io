"""
從內政部「不動產成交案件實際資訊資料供應系統」下載開放資料 ZIP。

兩種來源：
  current  當期資料（每月 1/11/21 發布，只含最近一期）
  season   分季封存（例：114S3 = 民國114年第3季）

當期檔案只有最近十天左右的登錄，要湊出一個建案的完整歷史，必須抓多個季別。
本專案的做法是：第一次執行時回補數季，之後每週只抓當期 + 最近一季，
再與 data/ 底下已存的紀錄合併去重。
"""

from __future__ import annotations

import io
import time
import zipfile
from datetime import date

import requests

BASE = "https://plvr.land.moi.gov.tw"
CURRENT_URL = f"{BASE}/Download?fileName=lvr_landcsv.zip&type=zip"
SEASON_URL = f"{BASE}/DownloadSeason?season={{season}}&fileName=lvr_landcsv.zip&type=zip"

HEADERS = {
    # 這個站對沒有 UA 的請求會擋，帶一個一般瀏覽器的 UA
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Referer": f"{BASE}/DownloadOpenData",
}

TIMEOUT = 120


def _get_zip(url: str, retries: int = 3) -> zipfile.ZipFile | None:
    """抓一個 ZIP 回來。失敗（含對方回 HTML 錯誤頁）時回 None。"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.content
            if not data[:2] == b"PK":
                # 對方偶爾會回一頁 HTML（維護中、季別不存在等）
                last_err = f"回傳的不是 ZIP（前 80 bytes: {data[:80]!r}）"
            else:
                return zipfile.ZipFile(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        if attempt < retries:
            time.sleep(5 * attempt)
    print(f"    下載失敗 {url}\n      {last_err}")
    return None


def fetch_current() -> zipfile.ZipFile | None:
    print("  下載當期資料 …")
    return _get_zip(CURRENT_URL)


def fetch_season(season: str) -> zipfile.ZipFile | None:
    print(f"  下載 {season} …")
    return _get_zip(SEASON_URL.format(season=season))


def recent_seasons(n: int, today: date | None = None) -> list[str]:
    """回傳最近 n 個季別代碼，新到舊，例：['115S2', '115S1', '114S4', ...]"""
    today = today or date.today()
    roc_year = today.year - 1911
    quarter = (today.month - 1) // 3 + 1
    out = []
    for _ in range(n):
        out.append(f"{roc_year}S{quarter}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            roc_year -= 1
    return out
