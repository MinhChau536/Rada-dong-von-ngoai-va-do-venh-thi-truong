"""
BỘ SINH DỮ LIỆU GIẢ LẬP – CHỈ DÙNG CHO KIỂM THỬ TỰ ĐỘNG (tests/).

Không được import từ src/: ứng dụng, PDF, bot chỉ dùng dữ liệu tải từ SSI/NEO.
Mô-đun ghi vào kho DuckDB TẠM của pytest (tmp_path) để kiểm thử chuỗi raw → fact → chỉ báo → phân tích
có đúng công thức, không nhìn trước và tái lập được – giống "fixture" trong kiểm thử phần mềm.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.common.config import get, stock_groups, ftse_universe
from src.common.logging import get_logger
from src.common.timeutil import fmt_ssi_date, today_vn
from src.data import database as db

log = get_logger(__name__)
SRC = "SSI"
SRC_NEO = "NEO"

# Ngày nghỉ lễ HOSE (gần đúng, chỉ dùng cho lịch mẫu)
HOLIDAYS = {
    "2025-04-30", "2025-05-01", "2025-05-02", "2025-09-01", "2025-09-02",
    "2026-01-01", "2026-01-02", "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-04-27", "2026-04-30", "2026-05-01", "2026-09-01", "2026-09-02",
}

# Vốn hóa ban đầu (tỷ đồng) và giá ban đầu (đồng) – độ lớn tương đối để chỉ số tập trung như thực tế
BIG = {
    "VCB": (480_000, 62_000), "BID": (250_000, 36_000), "CTG": (200_000, 37_000), "VIC": (160_000, 42_000),
    "VHM": (170_000, 40_000), "HPG": (170_000, 26_000), "FPT": (190_000, 120_000), "TCB": (170_000, 24_000),
    "GAS": (150_000, 64_000), "VPB": (150_000, 18_000), "MBB": (130_000, 21_000), "VNM": (125_000, 60_000),
    "GVR": (115_000, 28_000), "ACB": (110_000, 24_000), "MSN": (100_000, 64_000), "LPB": (80_000, 30_000),
    "HDB": (80_000, 22_000), "MWG": (80_000, 55_000), "SAB": (68_000, 52_000), "STB": (65_000, 37_000),
    "BCM": (62_000, 60_000), "VJC": (55_000, 98_000), "VIB": (55_000, 19_000), "SSI": (50_000, 23_000),
    "PLX": (45_000, 36_000), "SHB": (45_000, 11_000), "VRE": (45_000, 20_000), "SSB": (45_000, 17_000),
    "TPB": (40_000, 14_000), "DGC": (40_000, 100_000), "POW": (30_000, 12_000), "BVH": (35_000, 47_000),
    "VPL": (60_000, 70_000), "ACV": (90_000, 95_000), "BSR": (55_000, 18_000), "HVN": (45_000, 27_000),
    "EIB": (35_000, 19_000), "MSB": (30_000, 12_000), "OCB": (28_000, 11_000), "NVL": (25_000, 12_000),
}


def trading_days(start: date, end: date) -> List[pd.Timestamp]:
    days = pd.bdate_range(start, end)
    return [d for d in days if d.strftime("%Y-%m-%d") not in HOLIDAYS]


def tick(price: np.ndarray) -> np.ndarray:
    return np.where(price < 10_000, 10.0, np.where(price < 50_000, 50.0, 100.0))


def round_tick(p: np.ndarray) -> np.ndarray:
    t = tick(p)
    return np.round(p / t) * t


def ceil_floor(ref: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    up = ref * 1.07
    dn = ref * 0.93
    ceil_ = np.floor(up / tick(up)) * tick(up)
    floor_ = np.ceil(dn / tick(dn)) * tick(dn)
    return ceil_, floor_


def _s(x, nd=0) -> str:
    """SSI trả số dạng chuỗi."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    return f"{x:.{nd}f}"


class DemoMarket:
    """Mô phỏng thị trường HOSE; mọi tham số cố định bằng seed để tái lập."""

    def __init__(self, end: Optional[date] = None, seed: Optional[int] = None):
        self.seed = int(seed or 20251008)
        self.rng = np.random.default_rng(self.seed)
        self.start = pd.Timestamp(get("history.start_date", "2025-04-01")).date()
        self.end = end or today_vn()
        self.days = trading_days(self.start, self.end)
        g = stock_groups()
        self.groups = g
        self.symbols: List[str] = g["symbol"].tolist()
        self.sector = dict(zip(g["symbol"], g["sector"]))
        self.family = dict(zip(g["symbol"], g["family"]))
        self.vn30 = set(g.loc[g["in_vn30"], "symbol"])
        self.limit = dict(zip(g["symbol"], g["foreign_limit"]))
        self.ftse = set(ftse_universe()["symbol"]) if not ftse_universe().empty else set()

    # ── tham số mã ────────────────────────────────────────────────────────────
    def _params(self) -> pd.DataFrame:
        rng = self.rng
        rows = []
        for s in self.symbols:
            if s in BIG:
                cap, px = BIG[s]
                big = True
            else:
                cap = float(np.exp(rng.normal(np.log(5_500), 0.9)))
                cap = float(np.clip(cap, 600, 30_000))
                px = float(np.exp(rng.normal(np.log(22_000), 0.6)))
                px = float(np.clip(px, 4_000, 95_000))
                big = False
            shares = round(cap * 1e9 / px / 1000) * 1000
            rows.append({
                "symbol": s, "cap0": cap, "px0": float(round_tick(np.array([px]))[0]), "shares": shares, "big": big,
                "beta": rng.uniform(0.75, 1.25) if big else rng.uniform(0.6, 1.5),
                "idio": rng.uniform(0.010, 0.016) if big else rng.uniform(0.016, 0.028),
                "turnover": rng.uniform(0.0012, 0.004) if big else rng.uniform(0.003, 0.015),
                "fpr": rng.uniform(0.12, 0.30) if big else rng.uniform(0.02, 0.10),
                "treasury": rng.uniform(0.0, 0.03) if rng.random() < 0.15 else 0.0,
                "room_used0": rng.uniform(0.3, 0.99),
            })
        p = pd.DataFrame(rows).set_index("symbol")
        for s in ("FPT", "MWG", "REE", "PNJ"):           # room gần cạn như thực tế
            if s in p.index:
                p.loc[s, "room_used0"] = 0.985
        return p

    # (từ ngày, đến ngày, lợi suất lũy kế mục tiêu của nhân tố thị trường, độ lệch chuẩn ngày)
    REGIMES = [
        ("2025-04-01", "2025-04-09", -0.15, 0.020),   # cú sốc thuế quan đầu tháng 4/2025
        ("2025-04-10", "2025-04-18", 0.10, 0.015),
        ("2025-04-19", "2025-08-31", 0.36, 0.009),
        ("2025-09-01", "2025-10-31", -0.03, 0.013),
        ("2025-11-01", "2025-12-31", 0.03, 0.010),
        ("2026-01-01", "2026-06-30", -0.06, 0.010),   # nửa đầu 2026: số đông cổ phiếu đi xuống
        ("2026-07-01", "2026-08-31", 0.02, 0.011),
        ("2026-09-01", "2099-12-31", -0.02, 0.011),
    ]

    def _market_path(self) -> np.ndarray:
        """Nhân tố thị trường theo ngày; mỗi giai đoạn được hiệu chỉnh để đạt đúng lợi suất lũy kế mục tiêu."""
        m = np.zeros(len(self.days))
        ds = np.array([d.strftime("%Y-%m-%d") for d in self.days])
        for a, b, target, sd in self.REGIMES:
            idx = np.where((ds >= a) & (ds <= b))[0]
            if len(idx) == 0:
                continue
            x = self.rng.normal(0, sd, len(idx))
            x = x - x.mean() + np.log1p(target) / len(idx)
            m[idx] = np.expm1(x)
        return m

    def simulate(self) -> Dict[str, pd.DataFrame]:
        rng = self.rng
        P = self._params()
        syms = list(P.index)
        n = len(syms)
        sectors = sorted(set(self.sector.values()))
        sidx = np.array([sectors.index(self.sector[s]) for s in syms])
        is_vin = np.array([self.family.get(s) == "VINGROUP" for s in syms])
        is_ftse = np.array([s in self.ftse for s in syms])
        beta = P["beta"].values
        idio = P["idio"].values
        shares = P["shares"].values.astype(float)
        true_sh = shares * (1 - P["treasury"].values)
        room_total = np.array([self.limit[s] for s in syms]) * shares
        remain = room_total * (1 - P["room_used0"].values)
        ref = P["px0"].values.astype(float)
        fpr = P["fpr"].values
        tv_base = P["cap0"].values * 1e9 * P["turnover"].values
        nf_prev = np.zeros(n)
        ev = {"E1": pd.Timestamp("2025-10-08"), "E2": pd.Timestamp("2026-04-08"), "E3": pd.Timestamp("2026-09-18")}
        day_pos = {d: i for i, d in enumerate(self.days)}

        def pos_of(e):
            for d in self.days:
                if d >= e:
                    return day_pos[d]
            return 10 ** 9

        epos = {k: pos_of(v) for k, v in ev.items()}
        # Phát hành thêm (đổi ListedShare) cho 3 mã – để kiểm tra cờ room_changed & dim_securities theo ngày
        issuance = {"VPB": ("2025-11-17", 1.08), "SSI": ("2026-03-09", 1.15), "HDB": ("2026-06-15", 1.20)}
        m_path = self._market_path()
        is_big = P["big"].values.astype(float)
        idx = {"VNINDEX": 1317.20, "VN30": 1395.50, "HNXINDEX": 216.40, "UPCOMINDEX": 94.10}
        rows_s, rows_i, sec_hist = [], [], []
        for s in syms:
            sec_hist.append((s, self.days[0], shares[syms.index(s)]))
        for t, d in enumerate(self.days):
            ds = d.strftime("%Y-%m-%d")
            for s, (dt_iss, k) in issuance.items():
                if ds == dt_iss and s in syms:
                    j = syms.index(s)
                    shares[j] *= k
                    true_sh[j] *= k
                    room_total[j] *= k
                    remain[j] += (k - 1) * shares[j] / k * self.limit[s]
                    ref[j] = float(round_tick(np.array([ref[j] / k * 1.02]))[0])  # giá tham chiếu điều chỉnh quyền
                    sec_hist.append((s, d, shares[j]))
            m = m_path[t]
            f = rng.normal(0, 0.006, len(sectors))[sidx]
            e = rng.standard_t(4, n) / np.sqrt(2) * idio
            g_big = rng.normal(0, 0.009)                      # nhân tố vốn hóa lớn → chỉ số và số đông có thể lệch nhau
            r = beta * m + f + e + is_big * g_big - (1 - is_big) * 0.25 * g_big
            # Họ Vingroup kéo chỉ số nửa đầu 2026 (nghịch lý "chỉ số xanh, cổ phiếu đỏ")
            if "2026-01-01" <= ds < "2026-07-01":
                r += is_vin * 0.0042
            elif "2025-06-01" <= ds < "2025-12-31":
                r += is_vin * 0.0022
            # Hiệu ứng quanh mốc FTSE cho nhóm được đưa vào rổ
            tau1, tau3 = t - epos["E1"], t - epos["E3"]
            if tau1 in (0, 1):
                r += is_ftse * (0.009 if tau1 == 0 else 0.004)
            if -3 <= tau1 < 0:
                r += is_ftse * 0.0015
            if tau3 == 0:
                r += is_ftse * 0.006
            if tau3 in (1, 2):
                r += is_ftse * -0.003
            ceil_, floor_ = ceil_floor(ref)
            close = np.clip(round_tick(ref * (1 + r)), floor_, ceil_)
            # Tạm ngừng / không khớp lệnh (mã nhỏ, xác suất thấp)
            halted = (~P["big"].values) & (rng.random(n) < 0.004)
            close = np.where(halted, ref, close)
            ret = close / ref - 1
            liq = 1.0 + (0.35 if "2025-07-01" <= ds < "2025-09-01" else 0) + (0.25 if ds >= "2026-09-01" else 0)
            tv = tv_base * liq * np.exp(rng.normal(0, 0.35, n)) * (1 + 10 * np.abs(ret))
            if 0 <= tau3 <= 0:
                tv *= np.where(is_ftse, 2.6, 1.0)
            elif 1 <= tau3 <= 20:
                tv *= np.where(is_ftse, 1.15, 1.0)
            tv = np.where(halted, 0.0, tv)
            vol = np.round(tv / np.maximum(close, 1) / 100) * 100
            tv = vol * close * (1 + rng.normal(0, 0.002, n))           # giá trị ≈ KL × giá bình quân
            deal = np.where(rng.random(n) < 0.06, tv * rng.uniform(0.05, 0.6, n), 0.0)
            # Dòng vốn ngoại: bền (AR1), cùng chiều lợi suất, giai đoạn bán ròng kéo dài trước nâng hạng
            base = -0.035 if "2025-05-01" <= ds < "2026-09-01" else 0.005
            base_vec = np.full(n, base)
            if t >= epos["E3"]:
                base_vec = base_vec + is_ftse * 0.045
            if tau3 == 0:
                base_vec = base_vec + is_ftse * 0.28
            if -2 <= tau3 < 0:
                base_vec = base_vec + is_ftse * 0.05
            nf = 0.35 * nf_prev + base_vec + 1.6 * (ret / idio) * 0.04 + rng.normal(0, 0.09, n)
            nf = np.clip(nf, -1.8 * fpr, 1.8 * fpr)
            nf = np.where(halted, 0.0, nf)
            nf_prev = nf
            fb = tv * (fpr + nf / 2)
            fs = tv * (fpr - nf / 2)
            fb_vol = np.round(fb / np.maximum(close, 1) / 10) * 10
            fs_vol = np.round(fs / np.maximum(close, 1) / 10) * 10
            remain = np.clip(remain - (fb_vol - fs_vol), 0, room_total)
            hi = np.minimum(np.maximum(close, ref) * (1 + np.abs(rng.normal(0, 0.006, n))), ceil_)
            lo = np.maximum(np.minimum(close, ref) * (1 - np.abs(rng.normal(0, 0.006, n))), floor_)
            op = np.clip(round_tick(ref * (1 + rng.normal(0, 0.004, n))), lo, hi)
            hi, lo = round_tick(np.maximum(hi, np.maximum(op, close))), round_tick(np.minimum(lo, np.minimum(op, close)))
            hi, lo = np.minimum(hi, ceil_), np.maximum(lo, floor_)
            for j, s in enumerate(syms):
                rows_s.append({
                    "TradingDate": fmt_ssi_date(d), "Symbol": s, "Market": "HOSE",
                    "RefPrice": _s(ref[j]), "CeilingPrice": _s(ceil_[j]), "FloorPrice": _s(floor_[j]),
                    "OpenPrice": _s(op[j] if not halted[j] else 0), "HighestPrice": _s(hi[j] if not halted[j] else 0),
                    "LowestPrice": _s(lo[j] if not halted[j] else 0), "ClosePrice": _s(close[j]),
                    "PriceChange": _s(close[j] - ref[j]), "PerPriceChange": _s(ret[j] * 100, 2),
                    "TotalMatchVol": _s(vol[j]), "TotalMatchVal": _s(tv[j]),
                    "TotalDealVol": _s(np.round(deal[j] / close[j])), "TotalDealVal": _s(deal[j]),
                    "ForeignBuyVolTotal": _s(fb_vol[j]), "ForeignSellVolTotal": _s(fs_vol[j]),
                    "ForeignBuyValTotal": _s(fb[j]), "ForeignSellValTotal": _s(fs[j]),
                    "ForeignCurrentRoom": _s(remain[j]),
                })
            # Chỉ số: theo vốn hóa với số CP "thực" (trừ cổ phiếu quỹ) → sai số tái lập ε khác 0 như thực tế
            cap_ref, cap_close = (true_sh * ref), (true_sh * close)
            valid = ~halted
            r_vni = cap_close.sum() / cap_ref.sum() - 1 + rng.normal(0, 0.00008)
            v30 = np.array([s in self.vn30 for s in syms])
            r_v30 = cap_close[v30].sum() / cap_ref[v30].sum() - 1
            r_hnx = 0.6 * m + rng.normal(0, 0.008)
            r_upc = 0.35 * m + rng.normal(0, 0.005)
            adv, dec = int((close > ref).sum()), int((close < ref).sum())
            noc = n - adv - dec
            n_ce, n_fl = int((close >= ceil_).sum() - (halted & (close >= ceil_)).sum()), int((close <= floor_).sum())
            jitter = int(rng.random() < 0.08)  # đôi khi SSI đếm thêm CCQ/ETF → lệch 1 mã (kiểm tra B2.4)
            for code, rr, a, dcl, nc, vv, tt in (
                ("VNINDEX", r_vni, adv + jitter, dec, noc, vol[valid].sum(), tv[valid].sum()),
                ("VN30", r_v30, int((close > ref)[v30].sum()), int((close < ref)[v30].sum()),
                 int((close == ref)[v30].sum()), vol[v30].sum(), tv[v30].sum()),
                ("HNXINDEX", r_hnx, None, None, None, 6.8e7 * np.exp(rng.normal(0, .3)), 1.2e12 * np.exp(rng.normal(0, .3))),
                ("UPCOMINDEX", r_upc, None, None, None, 4.4e7 * np.exp(rng.normal(0, .3)), 6.5e11 * np.exp(rng.normal(0, .3))),
            ):
                prev = idx[code]
                val = prev * (1 + rr)
                o = prev * (1 + rng.normal(0, 0.002))
                h = max(o, val) * (1 + abs(rng.normal(0, 0.003)))
                lw = min(o, val) * (1 - abs(rng.normal(0, 0.003)))
                idx[code] = val
                rows_i.append({
                    "IndexId": code, "TradingDate": fmt_ssi_date(d), "IndexValue": _s(val, 2),
                    "Change": _s(val - prev, 2), "RatioChange": _s(rr * 100, 2),
                    "OpenIndex": _s(o, 2), "HighestIndex": _s(h, 2), "LowestIndex": _s(lw, 2),
                    "Advances": "" if a is None else str(a), "Declines": "" if dcl is None else str(dcl),
                    "NoChanges": "" if nc is None else str(nc),
                    "Ceilings": str(n_ce) if code == "VNINDEX" else "", "Floors": str(n_fl) if code == "VNINDEX" else "",
                    "TotalMatchVol": _s(vv), "TotalMatchVal": _s(tt), "TypeIndex": "Main", "TradingSession": "C",
                })
            ref = close.copy()
        return {"stock": pd.DataFrame(rows_s), "index": pd.DataFrame(rows_i),
                "sec": pd.DataFrame(sec_hist, columns=["symbol", "as_of", "shares"]), "params": P}

    # ── nến 5 phút ────────────────────────────────────────────────────────────
    def intraday(self, stock: pd.DataFrame, index: pd.DataFrame, sessions: int) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + 7)
        times = (["09:15"] + [f"{h:02d}:{m:02d}" for h in (9, 10, 11) for m in range(0, 60, 5)
                              if (h, m) > (9, 15) and (h, m) <= (11, 30)]
                 + [f"{h:02d}:{m:02d}" for h in (13, 14) for m in range(0, 60, 5) if (h, m) <= (14, 30)] + ["14:45"])
        k = len(times)
        last_days = self.days[-sessions:]
        syms = sorted(self.vn30)
        rows = []
        st = stock.copy()
        st["d"] = pd.to_datetime(st["TradingDate"], format="%d/%m/%Y")
        ix = index[index["IndexId"] == "VN30"].copy()
        ix["d"] = pd.to_datetime(ix["TradingDate"], format="%d/%m/%Y")
        P = self._params()
        for d in last_days:
            irow = ix[ix["d"] == d].iloc[0]
            i_open, i_close = float(irow["OpenIndex"]), float(irow["IndexValue"])
            inc = rng.normal(0, 0.0012, k)
            inc = inc - inc.mean() + np.log(i_close / i_open) / k
            ipath = i_open * np.exp(np.cumsum(inc))
            for code, path, o0 in (("VN30", ipath, i_open),):
                self._bars(rows, code, d, times, o0, path, rng, vol_scale=2e6)
            day = st[st["d"] == d].set_index("Symbol")
            for s in syms:
                if s not in day.index:
                    continue
                o, c = float(day.loc[s, "OpenPrice"] or 0), float(day.loc[s, "ClosePrice"])
                if o <= 0:
                    continue
                b = float(P.loc[s, "beta"]) if s in P.index else 1.0
                sinc = b * inc + rng.normal(0, 0.0018, k)
                sinc = sinc - sinc.mean() + np.log(c / o) / k
                spath = round_tick(o * np.exp(np.cumsum(sinc)))
                spath[-1] = c
                vol_day = float(day.loc[s, "TotalMatchVol"] or 0)
                self._bars(rows, s, d, times, o, spath, rng, vol_scale=vol_day / k)
        return pd.DataFrame(rows)

    @staticmethod
    def _bars(rows, sym, d, times, o0, path, rng, vol_scale):
        prev = o0
        for tm, c in zip(times, path):
            hi = max(prev, c) * (1 + abs(rng.normal(0, 0.0007)))
            lo = min(prev, c) * (1 - abs(rng.normal(0, 0.0007)))
            v = max(0.0, vol_scale * rng.lognormal(0, 0.5) * (3 if tm in ("09:15", "14:45") else 1))
            rows.append({"Symbol": sym, "TradingDate": fmt_ssi_date(d), "Time": f"{tm}:00",
                         "Open": _s(prev, 2), "High": _s(hi, 2), "Low": _s(lo, 2), "Close": _s(c, 2),
                         "Volume": _s(v), "Value": _s(v * c)})
            prev = c

    # ── luồng NEO mẫu ─────────────────────────────────────────────────────────
    def neo_stream(self, stock: pd.DataFrame, index: pd.DataFrame, sessions: int, watch: List[str]) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + 11)
        rows = []
        ix = index[index["IndexId"] == "VNINDEX"].copy()
        ix["d"] = pd.to_datetime(ix["TradingDate"], format="%d/%m/%Y")
        st = stock.copy()
        st["d"] = pd.to_datetime(st["TradingDate"], format="%d/%m/%Y")
        for d in self.days[-sessions:]:
            irow = ix[ix["d"] == d].iloc[0]
            o, c = float(irow["OpenIndex"]), float(irow["IndexValue"])
            minutes = [datetime.combine(d.date(), datetime.min.time()) + timedelta(hours=9, minutes=m) for m in range(0, 151)] + \
                      [datetime.combine(d.date(), datetime.min.time()) + timedelta(hours=13, minutes=m) for m in range(0, 106)]
            gap_start = rng.integers(20, len(minutes) - 20)          # một lần mất kết nối ngắn mỗi phiên
            gap_len = int(rng.integers(0, 3))
            path = np.linspace(o, c, len(minutes)) + rng.normal(0, 1.2, len(minutes)).cumsum() * 0.15
            path[-1] = c
            for k_, (ts, v) in enumerate(zip(minutes, path)):
                if gap_start <= k_ < gap_start + gap_len:
                    continue
                rows.append({"recv_ts": ts, "session_date": d.date(), "channel": "marketInfo", "symbol": "VNINDEX",
                             "payload": json.dumps({"marketCode": "VNINDEX", "indexValue": round(float(v), 2),
                                                    "advances": int(irow.get("Advances") or 0),
                                                    "declines": int(irow.get("Declines") or 0),
                                                    "marketStatus": "O" if ts.hour < 15 else "C"})})
            day = st[st["d"] == d].set_index("Symbol")
            for s in watch:
                if s not in day.index:
                    continue
                r = day.loc[s]
                for k_, ts in enumerate(minutes[::5]):
                    frac = (k_ + 1) / len(minutes[::5])
                    rows.append({"recv_ts": ts, "session_date": d.date(), "channel": "stockInfo", "symbol": s,
                                 "payload": json.dumps({"symbol": s, "closePrice": float(r["ClosePrice"]),
                                                        "foreignBuyValue": float(r["ForeignBuyValTotal"]) * frac,
                                                        "foreignSellValue": float(r["ForeignSellValTotal"]) * frac,
                                                        "foreignRemain": float(r["ForeignCurrentRoom"])})})
        df = pd.DataFrame(rows)
        df["source"] = SRC_NEO
        return df


def generate(end: Optional[date] = None, path=None, force: bool = False) -> Dict[str, int]:
    """Sinh và ghi dữ liệu mẫu vào các bảng raw_* (bỏ qua nếu đã có, trừ khi force=True)."""
    db.init_schema(path)
    existing = db.query_df("SELECT COUNT(*) AS n FROM raw_daily_stock WHERE source = ?", [SRC], path=path)
    if not force and not existing.empty and int(existing["n"].iloc[0]) > 0:
        log.info("Dữ liệu mẫu đã có – bỏ qua (force=False)")
        return {"skipped": 1}
    with db.connect(path=path) as con:
        for t in ("raw_daily_stock", "raw_daily_index", "raw_securities", "raw_index_components", "raw_intraday"):
            con.execute(f"DELETE FROM {t} WHERE source = ?", [SRC])
        con.execute("DELETE FROM raw_stream_neo WHERE source = ?", [SRC_NEO])
    mk = DemoMarket(end=end)
    log.info("Sinh dữ liệu mẫu %d phiên × %d mã …", len(mk.days), len(mk.symbols))
    sim = mk.simulate()
    now = datetime.now().replace(microsecond=0)
    stock, index = sim["stock"], sim["index"]
    rs = pd.DataFrame({
        "trade_date": pd.to_datetime(stock["TradingDate"], format="%d/%m/%Y").dt.date,
        "symbol": stock["Symbol"], "source": SRC,
        "payload": [json.dumps(r, ensure_ascii=False) for r in stock.to_dict("records")], "loaded_at": now})
    ri = pd.DataFrame({
        "trade_date": pd.to_datetime(index["TradingDate"], format="%d/%m/%Y").dt.date,
        "index_code": index["IndexId"], "source": SRC,
        "payload": [json.dumps(r) for r in index.to_dict("records")], "loaded_at": now})
    sec = sim["sec"]
    rsec = pd.DataFrame({
        "symbol": sec["symbol"], "as_of": pd.to_datetime(sec["as_of"]).dt.date, "source": SRC,
        "payload": [json.dumps({"Symbol": s, "SecType": "ST", "Exchange": "HOSE", "ListedShare": f"{sh:.0f}"})
                    for s, sh in zip(sec["symbol"], sec["shares"])], "loaded_at": now})
    comp = pd.DataFrame({"index_code": "VN30", "symbol": sorted(mk.vn30), "as_of": mk.days[0].date(),
                         "source": SRC, "loaded_at": now})
    intr = mk.intraday(stock, index, 20)
    rin = pd.DataFrame({
        "ts": pd.to_datetime(intr["TradingDate"] + " " + intr["Time"], format="%d/%m/%Y %H:%M:%S"),
        "symbol": intr["Symbol"], "source": SRC,
        "payload": [json.dumps(r) for r in intr.to_dict("records")], "loaded_at": now})
    neo = mk.neo_stream(stock, index, 10, list(get("watchlist_default", [])))
    with db.connect(path=path) as con:
        db.upsert("raw_daily_stock", rs, con=con)
        db.upsert("raw_daily_index", ri, con=con)
        db.upsert("raw_securities", rsec, con=con)
        db.upsert("raw_index_components", comp, con=con)
        db.upsert("raw_intraday", rin, con=con)
        con.register("_neo", neo)
        con.execute("INSERT INTO raw_stream_neo (recv_ts, session_date, channel, symbol, source, payload) "
                    "SELECT recv_ts, session_date, channel, symbol, source, payload FROM _neo")
    out = {"sessions": len(mk.days), "stock_rows": len(rs), "index_rows": len(ri), "intraday_rows": len(rin),
           "neo_rows": len(neo)}
    log.info("Đã ghi dữ liệu mẫu: %s", out)
    return out


