# Nguồn: kế thừa data/providers/base_provider.py – kho web_phantichchungkhoan (đồ án giữa kỳ),
# rút gọn: giữ khuôn lớp cơ sở (name, is_available, health_check), bỏ phương thức giá dành cho nguồn cũ.
"""Lớp cơ sở trừu tượng cho mọi nhà cung cấp dữ liệu (SSI, NEO)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict


class BaseProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def is_available(self) -> bool: ...

    def validate_symbol(self, symbol: str) -> str:
        return symbol.upper().strip()

    def health_check(self) -> Dict[str, Any]:
        return {"provider": self.name, "available": self.is_available, "timestamp": datetime.now().isoformat()}
