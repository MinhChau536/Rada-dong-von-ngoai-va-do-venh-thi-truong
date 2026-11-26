"""
Đẩy dữ liệu phiên mới lên GitHub để bản công khai (Streamlit Community Cloud) tự cập nhật.

    python -m tools.publish_data            # xuất data/snapshot_delta rồi commit + push đúng thư mục đó
    python -m tools.publish_data --no-push  # chỉ xuất, không đụng git

Chạy tự động sau khi tải xong số liệu cuối ngày (src/data/recorder_ssi.py, run.py) khi `publish.auto_push: true`
trong config/settings.yaml. Chỉ commit thư mục data/snapshot_delta (pathspec), KHÔNG BAO GIỜ đụng tới .env, báo cáo
hay tệp nào khác đang sửa dở. Vì SSI FastConnect yêu cầu đăng ký IP, máy chủ đám mây không tự gọi SSI được – dữ liệu
luôn do máy đã đăng ký IP tải về rồi đẩy lên.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DELTA_REL = "data/snapshot_delta"


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, check=check)


def publish(push: bool = True) -> dict:
    sys.path.insert(0, str(ROOT))
    from src.common.logging import get_logger
    from tools import snapshot
    log = get_logger("ffr.publish")
    man = snapshot.export_delta()
    last = str(man.get("last_session", ""))[:10]
    if not push:
        return {"state": "exported", "last_session": last}
    try:
        if _git("rev-parse", "--is-inside-work-tree", check=False).returncode != 0:
            return {"state": "no-git", "last_session": last}
        _git("add", "-A", "--", DELTA_REL)
        if _git("diff", "--cached", "--quiet", "--", DELTA_REL, check=False).returncode == 0:
            log.info("Dữ liệu trên GitHub đã mới (tới phiên %s) – không cần đẩy", last)
            return {"state": "unchanged", "last_session": last}
        _git("commit", "-m", f"Dữ liệu SSI tới phiên {last}", "--", DELTA_REL)
        r = _git("push", "origin", "HEAD", check=False)
        if r.returncode != 0:
            log.warning("Đẩy dữ liệu lên GitHub lỗi: %s", (r.stderr or r.stdout).strip()[:300])
            return {"state": "push-failed", "last_session": last}
        log.info("Đã đẩy dữ liệu tới phiên %s lên GitHub – bản công khai tự cập nhật sau 1–3 phút", last)
        return {"state": "pushed", "last_session": last}
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Không đẩy được dữ liệu lên GitHub: %s", exc)
        return {"state": "error", "last_session": last}


def auto_publish() -> dict:
    """Gọi sau mỗi lần cập nhật cuối ngày – tôn trọng cấu hình publish.auto_push."""
    sys.path.insert(0, str(ROOT))
    from src.common.config import get
    if not get("publish.auto_push", False):
        return {"state": "disabled"}
    return publish(push=True)


if __name__ == "__main__":
    print(publish(push="--no-push" not in sys.argv))
