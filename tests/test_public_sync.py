"""Bản công khai phải gọi bước nạp lại dữ liệu từ ảnh chụp trước khi đọc kho (đã từng bị xóa nhầm khi sửa menu)."""
from pathlib import Path


def test_main_calls_refresh_before_reading_store():
    src = (Path(__file__).resolve().parents[1] / "src" / "app" / "main.py").read_text(encoding="utf-8")
    assert "if refresh_from_snapshot():" in src
    assert src.index("if refresh_from_snapshot():") < src.index("if not da.ready():")
