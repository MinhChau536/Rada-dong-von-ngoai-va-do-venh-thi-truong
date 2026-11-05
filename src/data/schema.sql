-- ════════════════════════════════════════════════════════════════════════════
-- FTSE Flow Radar – Lược đồ DuckDB (bước B1.7). Chạy lại nhiều lần không lỗi.
-- Tầng raw_* lưu phản hồi GỐC (JSON) để tái lập; fact_* là bảng chuẩn; dim_* là danh mục;
-- indicator_* do pipeline (src/analytics/pipeline.py) tạo lại toàn bộ bằng CREATE OR REPLACE.
-- Mọi dấu thời gian theo giờ Việt Nam (Asia/Ho_Chi_Minh), lưu dạng TIMESTAMP không múi giờ.
-- ════════════════════════════════════════════════════════════════════════════

-- ── RAW ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS raw_daily_stock (
    trade_date DATE NOT NULL, symbol VARCHAR NOT NULL, source VARCHAR NOT NULL,
    payload VARCHAR NOT NULL, loaded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (trade_date, symbol, source));

CREATE TABLE IF NOT EXISTS raw_daily_index (
    trade_date DATE NOT NULL, index_code VARCHAR NOT NULL, source VARCHAR NOT NULL,
    payload VARCHAR NOT NULL, loaded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (trade_date, index_code, source));

CREATE TABLE IF NOT EXISTS raw_securities (
    symbol VARCHAR NOT NULL, as_of DATE NOT NULL, source VARCHAR NOT NULL,
    payload VARCHAR NOT NULL, loaded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (symbol, as_of, source));

CREATE TABLE IF NOT EXISTS raw_index_components (
    index_code VARCHAR NOT NULL, symbol VARCHAR NOT NULL, as_of DATE NOT NULL, source VARCHAR NOT NULL,
    loaded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (index_code, symbol, as_of, source));

CREATE TABLE IF NOT EXISTS raw_intraday (
    ts TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, source VARCHAR NOT NULL,
    payload VARCHAR NOT NULL, loaded_at TIMESTAMP NOT NULL,
    PRIMARY KEY (ts, symbol, source));

CREATE SEQUENCE IF NOT EXISTS seq_stream START 1;
CREATE TABLE IF NOT EXISTS raw_stream (          -- SSI streaming: MI, R, X-TRADE, F
    id BIGINT DEFAULT nextval('seq_stream'), recv_ts TIMESTAMP NOT NULL, session_date DATE,
    channel VARCHAR, symbol VARCHAR, source VARCHAR DEFAULT 'SSI', payload VARCHAR);

CREATE SEQUENCE IF NOT EXISTS seq_stream_neo START 1;
CREATE TABLE IF NOT EXISTS raw_stream_neo (      -- NEO WebSocket: marketInfo, marketSession, stockInfo (B1.4b)
    id BIGINT DEFAULT nextval('seq_stream_neo'), recv_ts TIMESTAMP NOT NULL, session_date DATE,
    channel VARCHAR, symbol VARCHAR, source VARCHAR DEFAULT 'NEO', payload VARCHAR);

-- ── FACT ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS fact_daily_stock (
    trade_date DATE NOT NULL, symbol VARCHAR NOT NULL, source VARCHAR NOT NULL,
    ref DOUBLE, ceiling DOUBLE, floor DOUBLE, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
    vol DOUBLE, tv DOUBLE, vol_pt DOUBLE, tv_pt DOUBLE,
    fb_vol DOUBLE, fs_vol DOUBLE, fb DOUBLE, fs DOUBLE, remain DOUBLE, room DOUBLE,
    loaded_at TIMESTAMP,
    PRIMARY KEY (trade_date, symbol));

CREATE TABLE IF NOT EXISTS fact_daily_index (
    trade_date DATE NOT NULL, index_code VARCHAR NOT NULL, source VARCHAR NOT NULL,
    value DOUBLE, change DOUBLE, ratio_change DOUBLE, open DOUBLE, high DOUBLE, low DOUBLE,
    advances INTEGER, declines INTEGER, no_changes INTEGER, ceilings INTEGER, floors INTEGER,
    vol DOUBLE, tv DOUBLE, loaded_at TIMESTAMP,
    PRIMARY KEY (trade_date, index_code));

CREATE TABLE IF NOT EXISTS fact_intraday (
    ts TIMESTAMP NOT NULL, symbol VARCHAR NOT NULL, source VARCHAR NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, vol DOUBLE,
    PRIMARY KEY (ts, symbol));

-- ── DIM ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dim_securities (
    symbol VARCHAR NOT NULL, sec_type VARCHAR, exchange VARCHAR, listed_share DOUBLE,
    as_of DATE NOT NULL, source VARCHAR, loaded_at TIMESTAMP,
    PRIMARY KEY (symbol, as_of));

CREATE TABLE IF NOT EXISTS dim_universe (
    universe VARCHAR NOT NULL, symbol VARCHAR NOT NULL, effective_date DATE, source VARCHAR,
    PRIMARY KEY (universe, symbol));

CREATE TABLE IF NOT EXISTS dim_events (
    event_id VARCHAR PRIMARY KEY, event_date DATE, effective_date DATE,
    label VARCHAR, description VARCHAR, source_url VARCHAR);

-- ── ỨNG DỤNG & VẬN HÀNH ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS watchlist (
    symbol VARCHAR PRIMARY KEY, added_at TIMESTAMP, note VARCHAR);

CREATE TABLE IF NOT EXISTS alert_log (
    event_id VARCHAR NOT NULL, ts TIMESTAMP NOT NULL, trade_date DATE, alert_type VARCHAR,
    rule_no INTEGER, symbol VARCHAR, priority VARCHAR, message VARCHAR,
    status VARCHAR,                -- sent | suppressed_cooldown | suppressed_limit | simulated
    channel VARCHAR, mode VARCHAR  -- live | backtest
);

CREATE SEQUENCE IF NOT EXISTS seq_reports START 1;
CREATE TABLE IF NOT EXISTS reports_log (
    id BIGINT DEFAULT nextval('seq_reports'), created_at TIMESTAMP, kind VARCHAR, trade_date DATE,
    path VARCHAR, status VARCHAR, note VARCHAR);

CREATE TABLE IF NOT EXISTS source_events (
    ts TIMESTAMP NOT NULL, from_source VARCHAR, to_source VARCHAR, reason VARCHAR);

CREATE TABLE IF NOT EXISTS source_status (
    source VARCHAR PRIMARY KEY, status VARCHAR, last_ok TIMESTAMP, last_error TIMESTAMP,
    message VARCHAR, updated_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS data_quality_log (
    trade_date DATE, check_name VARCHAR, metric VARCHAR, value DOUBLE, status VARCHAR,
    detail VARCHAR, created_at TIMESTAMP);

CREATE TABLE IF NOT EXISTS ingest_log (
    ts TIMESTAMP, source VARCHAR, endpoint VARCHAR, status VARCHAR, n_rows INTEGER,
    attempts INTEGER, elapsed_ms DOUBLE, message VARCHAR);

CREATE TABLE IF NOT EXISTS checkpoints (
    job VARCHAR PRIMARY KEY, last_value VARCHAR, updated_at TIMESTAMP);

-- ── CHỈ BÁO (tạo bởi pipeline, mô tả để tra cứu) ────────────────────────────
-- indicator_daily        : 1 dòng/phiên  – D, AD, IQR, CR5, ε, NF, HHI, z, loại phiên, phân vị 20/60/250 …
-- indicator_stock_daily  : mã × phiên   – r, w, C, NF, nf, FPR, z_nf, pct60_nf, streak, U, absorb_state, ER …
-- indicator_group_daily  : nhóm × phiên – đóng góp & dòng vốn theo ngành, họ cổ phiếu, FTSE, đối chứng, VN30
-- leaders_daily          : top 5 đóng góp dương/âm mỗi phiên
-- indicator_intraday     : chỉ báo trong phiên từ nến 5 phút
-- indicator_watchlist    : hồ sơ phản ứng từng mã watchlist
-- event_params, event_results, event_aar, did_coefs, stats_results : Module C
