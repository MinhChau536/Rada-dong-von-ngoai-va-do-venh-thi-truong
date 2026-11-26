"""
Ảnh chụp kho dữ liệu để chia sẻ qua GitHub (tệp data/ffr.duckdb ~850 MB vượt giới hạn 100 MB/tệp của GitHub).

    python -m tools.snapshot export     # kho → data/snapshot/<bảng>/*.parquet (zstd, mỗi tệp < 45 MB) + manifest.json
    python -m tools.snapshot restore    # data/snapshot → data/ffr.duckdb (tự chạy khi mở app mà chưa có kho)
    python -m tools.snapshot verify     # so số dòng kho hiện tại với manifest
    python -m tools.snapshot delta      # chỉ các phiên mới kể từ ảnh gốc → data/snapshot_delta (vài MB, đẩy hằng ngày)

Ảnh gốc (data/snapshot, ~265 MB) ít khi đổi; mỗi phiên mới chỉ cần đẩy data/snapshot_delta: bảng lớn có cột trade_date
lấy các dòng từ phiên cuối của ảnh gốc trở đi, bảng nhỏ lấy nguyên bảng. Khôi phục = ảnh gốc rồi áp phần bổ sung.

Khôi phục: tạo lược đồ từ src/data/schema.sql rồi nạp từng bảng (INSERT BY NAME; bảng ngoài lược đồ → CREATE AS),
nên khóa chính/ràng buộc giữ nguyên như kho gốc. Dữ liệu là dữ liệu thật tải từ SSI FastConnect V3.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Optional

import duckdb

ROOT = Path(__file__).resolve().parents[1]
SNAP = ROOT / "data" / "snapshot"
DELTA = ROOT / "data" / "snapshot_delta"
LIVE_SNAP = ROOT / "data" / "live_snapshot"          # số liệu TRONG PHIÊN của hôm nay (vài trăm KB, đẩy mỗi ~2 phút)
LIVE_STAMP = ROOT / "data" / ".live_stamp"
STAMP = ROOT / "data" / ".snapshot_stamp"
BIG_ROWS = 20000
CHUNK = "45MB"


def _print(*a, **k) -> None:
    """In an toàn: console Windows mã cp1252 hoặc pythonw (không có stdout) không làm hỏng việc xuất dữ liệu."""
    try:
        print(*a, **k)
    except (UnicodeEncodeError, OSError, AttributeError, ValueError):
        pass


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def export(db: Optional[Path] = None, out: Path = SNAP) -> Dict:
    from src.common.config import db_path
    db = Path(db or db_path())
    tmp = out.with_name(out.name + "_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    con = duckdb.connect(str(db), read_only=True)
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
                                        "AND table_type = 'BASE TABLE' ORDER BY 1").fetchall()]
    man = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "source": "SSI FastConnect V3", "tables": {}}
    for t in tables:
        n = con.execute(f"SELECT COUNT(*) FROM {_q(t)}").fetchall()[0][0]
        d = tmp / t
        con.execute(f"COPY {_q(t)} TO '{d.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, "
                    f"FILE_SIZE_BYTES '{CHUNK}', OVERWRITE_OR_IGNORE)")
        files = sorted(p.name for p in d.glob("*.parquet"))
        man["tables"][t] = {"rows": int(n), "files": files}
        _print(f"  {t:34s} {n:>10,} dòng · {len(files)} tệp", flush=True)
    for k, sql in (("last_session", "SELECT MAX(trade_date) FROM indicator_daily"),):
        try:
            man[k] = str(con.execute(sql).fetchall()[0][0])
        except duckdb.Error:
            pass
    con.close()
    (tmp / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    size = sum(p.stat().st_size for p in out.rglob("*.parquet")) / 1e6
    _print(f"Đã xuất {len(tables)} bảng → {out} ({size:,.0f} MB)")
    return man


def restore(db: Optional[Path] = None, src: Path = SNAP, force: bool = False) -> bool:
    from src.common.config import db_path
    db = Path(db or db_path())
    man_f = src / "manifest.json"
    if not man_f.exists():
        return False
    if db.exists() and not force:
        _print(f"{db} đã có – bỏ qua (dùng --force để ghi đè)")
        return False
    man = json.loads(man_f.read_text(encoding="utf-8"))
    tmp = db.with_suffix(".restoring")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute((ROOT / "src" / "data" / "schema.sql").read_text(encoding="utf-8"))
    have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
    for t, info in man["tables"].items():
        files = [(src / t / f).as_posix() for f in info["files"]]
        if not files:
            continue
        rp = "read_parquet([" + ",".join(f"'{f}'" for f in files) + "])"
        if t in have:
            con.execute(f"INSERT INTO {_q(t)} BY NAME SELECT * FROM {rp}")
        else:
            con.execute(f"CREATE TABLE {_q(t)} AS SELECT * FROM {rp}")
    expect = {t: i["rows"] for t, i in man["tables"].items()}
    dman = _delta_manifest(man) if src == SNAP else None
    if dman:
        for t, i in dman["tables"].items():
            files = [(DELTA / t / f).as_posix() for f in i["files"]]
            if t not in expect and not files:
                continue
            if i["mode"] == "after":
                con.execute(f"DELETE FROM {_q(t)} WHERE CAST(trade_date AS DATE) >= DATE '{dman['base_last']}'")
            elif t in expect:
                con.execute(f"DELETE FROM {_q(t)}")
            if files:
                rp = "read_parquet([" + ",".join(f"'{f}'" for f in files) + "])"
                exists = con.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?", [t]).fetchall()[0][0]
                con.execute(f"INSERT INTO {_q(t)} BY NAME SELECT * FROM {rp}" if exists else f"CREATE TABLE {_q(t)} AS SELECT * FROM {rp}")
            expect[t] = i["total_rows"]
    bad = {t: (con.execute(f"SELECT COUNT(*) FROM {_q(t)}").fetchall()[0][0], n) for t, n in expect.items()}
    bad = {t: v for t, v in bad.items() if v[0] != v[1]}
    con.close()
    if bad:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Khôi phục lệch số dòng: {bad}")
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    tmp.rename(db)
    try:
        STAMP.write_text(stamp(), encoding="utf-8")
    except OSError:
        pass
    last = (dman or man).get("last_session", "?")
    _print(f"Đã khôi phục {len(man['tables'])} bảng → {db} (dữ liệu tới phiên {last})")
    return True


def _delta_manifest(base: Dict) -> Optional[Dict]:
    f = DELTA / "manifest.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text(encoding="utf-8"))
    return d if d.get("base_created") == base.get("created") else None      # delta của ảnh gốc khác → bỏ qua


def stamp() -> str:
    """Dấu phiên bản dữ liệu đang có trên đĩa (ảnh gốc + phần bổ sung) – đổi khi có dữ liệu mới được đẩy lên."""
    parts = []
    for f in (SNAP / "manifest.json", DELTA / "manifest.json"):
        try:
            parts.append(json.loads(f.read_text(encoding="utf-8")).get("created", ""))
        except (OSError, ValueError):
            parts.append("")
    return "|".join(parts)


def export_live(live_db: Optional[Path] = None) -> Optional[Dict]:
    """Xuất các dòng của phiên hôm nay từ data/live.duckdb → data/live_snapshot/ (để bản công khai có số liệu trong phiên)."""
    from src.data import live
    src_db = Path(live_db or live.LIVE_DB)
    if not src_db.exists():
        return None
    con = duckdb.connect(str(src_db), read_only=True)
    try:
        m = con.execute("SELECT * FROM live_meta").df()
        if m.empty:
            return None
        sess = str(m["session_date"].iloc[0])[:10]
        tmp = LIVE_SNAP.with_name(LIVE_SNAP.name + "_tmp")
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        dated = {r[0] for r in con.execute("SELECT table_name FROM information_schema.columns WHERE table_schema = 'main' "
                                           "AND column_name = 'trade_date'").fetchall()}
        man = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "session_date": sess,
               "built_at": str(m["built_at"].iloc[0]) if "built_at" in m else "", "tables": {}}
        for t in sorted(dated | {"live_meta", "pipeline_meta"}):
            sel = (f"SELECT * FROM {_q(t)} WHERE CAST(trade_date AS DATE) = DATE '{sess}'" if t in dated
                   else f"SELECT * FROM {_q(t)}")
            n = int(con.execute(f"SELECT COUNT(*) FROM ({sel})").fetchall()[0][0])
            if not n:
                continue
            f = tmp / f"{t}.parquet"
            con.execute(f"COPY ({sel}) TO '{f.as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
            man["tables"][t] = {"rows": n, "file": f.name}
    finally:
        con.close()
    (tmp / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(LIVE_SNAP, ignore_errors=True)
    tmp.rename(LIVE_SNAP)
    return man


def live_stamp() -> str:
    try:
        return json.loads((LIVE_SNAP / "manifest.json").read_text(encoding="utf-8")).get("created", "")
    except (OSError, ValueError):
        return ""


def restore_live(out: Optional[Path] = None) -> bool:
    """Bản công khai: dựng data/live.duckdb từ data/live_snapshot/ (giao diện ghép phiên này sau dữ liệu lịch sử)."""
    from src.data import live
    man_f = LIVE_SNAP / "manifest.json"
    out = Path(out or live.LIVE_DB)
    if not man_f.exists():
        return False
    man = json.loads(man_f.read_text(encoding="utf-8"))
    tmp = out.with_name(out.stem + "_restoring.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    for t, i in man["tables"].items():
        con.execute(f"CREATE TABLE {_q(t)} AS SELECT * FROM read_parquet('{(LIVE_SNAP / i['file']).as_posix()}')")
    con.close()
    import os
    os.replace(tmp, out)
    try:
        LIVE_STAMP.write_text(man.get("created", ""), encoding="utf-8")
    except OSError:
        pass
    return True


def export_delta(db: Optional[Path] = None) -> Dict:
    """Xuất phần bổ sung so với ảnh gốc data/snapshot."""
    from src.common.config import db_path
    base = json.loads((SNAP / "manifest.json").read_text(encoding="utf-8"))
    base_last = str(base.get("last_session", ""))[:10]
    tmp = DELTA.with_name(DELTA.name + "_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    con = duckdb.connect(str(db or db_path()), read_only=True)
    tables = [r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' "
                                        "AND table_type = 'BASE TABLE' ORDER BY 1").fetchall()]
    dated = {r[0] for r in con.execute("SELECT table_name FROM information_schema.columns WHERE table_schema = 'main' "
                                       "AND column_name = 'trade_date'").fetchall()}
    man = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "base_created": base.get("created"), "base_last": base_last,
           "source": "SSI FastConnect V3", "tables": {}}
    for t in tables:
        total = int(con.execute(f"SELECT COUNT(*) FROM {_q(t)}").fetchall()[0][0])
        after = t in dated and base["tables"].get(t, {}).get("rows", 0) >= BIG_ROWS
        sel = (f"SELECT * FROM {_q(t)} WHERE CAST(trade_date AS DATE) >= DATE '{base_last}'" if after
               else f"SELECT * FROM {_q(t)}")
        n = int(con.execute(f"SELECT COUNT(*) FROM ({sel})").fetchall()[0][0])
        files = []
        if n:
            d = tmp / t
            con.execute(f"COPY ({sel}) TO '{d.as_posix()}' (FORMAT parquet, COMPRESSION zstd, COMPRESSION_LEVEL 9, "
                        f"FILE_SIZE_BYTES '{CHUNK}', OVERWRITE_OR_IGNORE)")
            files = sorted(p.name for p in d.glob("*.parquet"))
        man["tables"][t] = {"mode": "after" if after else "full", "rows": n, "total_rows": total, "files": files}
    try:
        man["last_session"] = str(con.execute("SELECT MAX(trade_date) FROM indicator_daily").fetchall()[0][0])
    except duckdb.Error:
        pass
    con.close()
    (tmp / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
    shutil.rmtree(DELTA, ignore_errors=True)
    tmp.rename(DELTA)
    size = sum(p.stat().st_size for p in DELTA.rglob("*.parquet")) / 1e6
    _print(f"Đã xuất phần bổ sung tới phiên {man.get('last_session', '?')[:10]} → {DELTA} ({size:,.1f} MB)")
    return man


def verify(db: Optional[Path] = None, src: Path = SNAP) -> bool:
    from src.common.config import db_path
    man = json.loads((src / "manifest.json").read_text(encoding="utf-8"))
    con = duckdb.connect(str(db or db_path()), read_only=True)
    ok = True
    expect = {t: i["rows"] for t, i in man["tables"].items()}
    dman = _delta_manifest(man) if src == SNAP else None
    if dman:
        expect.update({t: i["total_rows"] for t, i in dman["tables"].items()})
    for t, rows in expect.items():
        n = con.execute(f"SELECT COUNT(*) FROM {_q(t)}").fetchall()[0][0]
        if n != rows:
            ok = False
            _print(f"  LỆCH {t}: kho {n} ≠ ảnh chụp {rows}")
    con.close()
    _print("Khớp manifest" if ok else "Có bảng lệch")
    return ok


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    cmd = sys.argv[1] if len(sys.argv) > 1 else "export"
    if cmd == "export":
        export()
    elif cmd == "restore":
        restore(force="--force" in sys.argv)
    elif cmd == "delta":
        export_delta()
    elif cmd == "verify":
        sys.exit(0 if verify() else 1)
    else:
        _print(__doc__)
