"""
中文轉通用拼音（Tongyong Pinyin），用來產生網址代號。

pypinyin 只輸出漢語拼音，所以先取漢語拼音（不帶聲調），再逐音節套用
通用拼音的轉換規則。規則依教育部公告的對照表整理，主要差異：

    聲母    zh → jh      q → c       x → s
    空韻    zhi/chi/shi/ri → jhih/chih/shih/rih
            zi/ci/si       → zih/cih/sih
    撮口    ju/qu/xu → jyu/cyu/syu    nü/lü → nyu/lyu
    韻母    -iu → -iou   -ui → -uei
    特例    feng → fong  wen → wun   weng → wong

驗證基準：勝興豐川 → shengsingfongchuan（與本專案 repo 名稱相符）。
"""

from __future__ import annotations

import re

try:
    from pypinyin import Style, pinyin
except ImportError:  # 沒裝套件時不讓整個流程掛掉，改用雜湊代號
    pinyin = None
    Style = None

# 空韻：拼音以 i 結尾且聲母為捲舌音／平舌音時，i 要寫成 ih
_EMPTY_RHYME = {
    "zhi": "jhih", "chi": "chih", "shi": "shih", "ri": "rih",
    "zi": "zih", "ci": "cih", "si": "sih",
}

# 整個音節直接對應的特例
_WHOLE = {
    "feng": "fong",
    "wen": "wun",
    "weng": "wong",
    "yu": "yu", "yue": "yue", "yuan": "yuan", "yun": "yun",
}

# 撮口呼：j/q/x 後的 u 實際是 ü，通用拼音寫作 yu
_JQX_U = {"j": "jy", "q": "cy", "x": "sy"}


def syllable(hanyu: str) -> str:
    """單一音節的漢語拼音 → 通用拼音。"""
    s = hanyu.lower()

    if s in _EMPTY_RHYME:
        return _EMPTY_RHYME[s]
    if s in _WHOLE:
        return _WHOLE[s]

    # ü 的各種寫法統一成 yu：nü → nyu、lüe → lyue
    s = s.replace("ü", "yu").replace("v", "yu")

    # j/q/x + u 其實是 ü
    if len(s) > 1 and s[0] in _JQX_U and s[1] == "u":
        s = _JQX_U[s[0]] + s[2:]
    else:
        # 聲母轉換，順序重要：zh 要在 z 之前處理
        if s.startswith("zh"):
            s = "jh" + s[2:]
        elif s.startswith("q"):
            s = "c" + s[1:]
        elif s.startswith("x"):
            s = "s" + s[1:]

    # 韻母：-iu → -iou、-ui → -uei（需排除 gui 之外無此形的情況，故用結尾比對）
    if s.endswith("iu"):
        s = s[:-2] + "iou"
    elif s.endswith("ui"):
        s = s[:-2] + "uei"

    return s


def romanize(text: str) -> str:
    """把字串裡的中文轉成通用拼音，非中文的英數字原樣保留。

    不含聲調符號、不含空白。轉不出來時回傳空字串，呼叫端可據此改用備援代號。
    """
    if pinyin is None:
        return ""

    out = []
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            got = pinyin(ch, style=Style.NORMAL, errors="ignore")
            if got and got[0]:
                out.append(syllable(got[0][0]))
        elif ch.isalnum():
            out.append(ch)
        # 其餘字元（空白、標點、底線等）直接捨棄

    slug = "".join(out).lower()
    return re.sub(r"[^a-z0-9]", "", slug)
