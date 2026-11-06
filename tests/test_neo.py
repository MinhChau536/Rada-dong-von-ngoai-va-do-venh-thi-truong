"""Kiểm thử lớp NEO: định dạng đăng ký WebSocket, giải mã Avro, quy đổi đơn vị ảnh chụp cuối phiên (không cần mạng)."""
import base64
import io
import json
import zlib

import pandas as pd
import pytest

from src.data.neo_eod import unit_factors
from src.neo_api.neo_client import NEOClient, default_subscriptions


def test_subscriptions_follow_sdk_format_and_batch():
    subs = default_subscriptions([f"A{i:02d}" for i in range(150)] + ["FPT", "FPT"])
    assert subs[0] == {"type": "sub", "channel": "marketInfo", "listId": ["VNINDEX", "VN30", "HNXINDEX", "UPCOMINDEX"]}
    stock = [s for s in subs if s["channel"] == "stockInfo"]
    assert [len(s["listId"]) for s in stock] == [100, 51]          # lô 100 mã, bỏ trùng
    assert all(s["type"] == "sub" for s in subs)


def test_avro_decode_with_schema_id_prefix():
    avro = pytest.importorskip("avro")
    import avro.io
    import avro.schema

    schema = {"type": "record", "name": "StockInfo", "fields": [{"name": "symbol", "type": "string"},
                                                                 {"name": "closePrice", "type": ["null", "double"]}]}
    blob = base64.b64encode(zlib.compress(json.dumps({"3": schema}).encode()))
    c = NEOClient(username="u", password="p")
    c._load_schemas(blob)
    buf = io.BytesIO()
    avro.io.DatumWriter(avro.schema.parse(json.dumps(schema))).write({"symbol": "FPT", "closePrice": 120.5},
                                                                   avro.io.BinaryEncoder(buf))
    rec = c.decode(bytes([3]) + buf.getvalue())
    assert rec == {"symbol": "FPT", "closePrice": 120.5, "_channel": "stockInfo"}
    assert c.decode(bytes([99]) + b"x") is None                    # lược đồ lạ → bỏ qua, không lỗi


def test_unit_factors_detect_thousand_price_and_million_value():
    # giá theo nghìn đồng, giá trị theo triệu đồng: 1 000 000 cp × 120 500 đ = 120,5 tỷ = 120 500 triệu
    recs = pd.DataFrame({"refPrice": [120.0, 25.0], "closePrice": [120.5, 25.0],
                         "totalTradingVolume": [1_000_000, 2_000_000], "totalTradingValue": [120_500.0, 50_000.0]})
    assert unit_factors(recs) == (1000.0, 1_000_000.0)
    vnd = pd.DataFrame({"refPrice": [120000.0], "closePrice": [120500.0], "totalTradingVolume": [1_000_000],
                        "totalTradingValue": [120_500_000_000.0]})
    assert unit_factors(vnd) == (1.0, 1.0)
