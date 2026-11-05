"""
Tin liên quan (bước B7.7 – tùy chọn, nguồn BỔ TRỢ ngoài SSI/NEO).
Rút gọn từ core/tin_tuc.py của đồ án giữa kỳ: chỉ đọc Google News RSS, có timeout, lỗi thì trả rỗng.
Giao diện luôn ghi nhãn "Nguồn ngoài SSI/NEO".
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List
from urllib.parse import quote

import requests

from src.common.logging import get_logger

log = get_logger(__name__)
UA = {"User-Agent": "FTSE-Flow-Radar/3.2 (academic project)"}


def latest(symbol: str, n: int = 3, timeout: float = 5.0) -> List[Dict]:
    q = quote(f'"{symbol}" cổ phiếu')
    url = f"https://news.google.com/rss/search?q={q}&hl=vi&gl=VN&ceid=VN:vi"
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        for it in root.iter("item"):
            out.append({"title": (it.findtext("title") or "").strip(), "link": it.findtext("link") or "",
                        "date": it.findtext("pubDate") or "", "source": it.findtext("source") or "Google News"})
            if len(out) >= n:
                break
        return out
    except Exception as exc:  # mạng chặn / RSS đổi định dạng → không làm dừng trang
        log.info("Không lấy được tin %s: %s", symbol, exc)
        return []
