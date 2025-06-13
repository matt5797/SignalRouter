-- SignalRouter 자동매매 시스템 데이터베이스 스키마

-- 계좌 관리
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('STOCK', 'FUTURES')),
    secret_file_path TEXT NOT NULL,
    is_virtual BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 계좌별 잔고
CREATE TABLE IF NOT EXISTS balances (
    account_id TEXT PRIMARY KEY,
    total_balance DECIMAL(15,2) NOT NULL DEFAULT 0,
    available_balance DECIMAL(15,2) NOT NULL DEFAULT 0,
    unrealized_pnl DECIMAL(15,2) NOT NULL DEFAULT 0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

-- 전략 설정
CREATE TABLE IF NOT EXISTS strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    webhook_token TEXT NOT NULL UNIQUE,
    max_position_ratio DECIMAL(5,4) NOT NULL DEFAULT 0.2,
    max_daily_loss DECIMAL(15,2) NOT NULL DEFAULT 500000,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

-- 거래 내역
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT NOT NULL,
    strategy_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    transition_type TEXT NOT NULL CHECK (transition_type IN ('ENTRY', 'EXIT', 'REVERSE')),
    quantity INTEGER NOT NULL,
    price DECIMAL(10,2),
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price DECIMAL(10,2),
    commission DECIMAL(10,2) DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'SIGNAL' CHECK (status IN ('SIGNAL', 'PENDING', 'FILLED', 'FAILED')),
    broker_order_id TEXT,
    signal_data TEXT,
    signal_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    fill_time DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- 포지션 관리
CREATE TABLE IF NOT EXISTS positions (
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_price DECIMAL(10,2) NOT NULL DEFAULT 0,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, symbol),
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

-- 성능 인덱스 (이미 존재하는 경우 무시)
CREATE INDEX IF NOT EXISTS idx_trades_account_symbol ON trades(account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_trades_strategy_time ON trades(strategy_id, signal_time);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_strategies_webhook ON strategies(webhook_token);

-- 포지션 자동 업데이트 트리거 (이미 존재할 수 있으므로 DROP 후 재생성)
DROP TRIGGER IF EXISTS update_position_after_fill;
CREATE TRIGGER update_position_after_fill
AFTER UPDATE ON trades
WHEN NEW.status = 'FILLED' AND OLD.status != 'FILLED'
BEGIN
    INSERT OR REPLACE INTO positions (account_id, symbol, quantity, avg_price, last_updated)
    VALUES (
        NEW.account_id,
        NEW.symbol,
        COALESCE((SELECT quantity FROM positions WHERE account_id = NEW.account_id AND symbol = NEW.symbol), 0) +
        CASE WHEN NEW.action = 'BUY' THEN NEW.filled_quantity ELSE -NEW.filled_quantity END,
        NEW.avg_fill_price,
        CURRENT_TIMESTAMP
    );
END;

-- 샘플 데이터 (중복 방지)
INSERT OR IGNORE INTO accounts (account_id, name, account_type, secret_file_path, is_virtual) VALUES
('stock_real_01', '주식 실전 계좌', 'STOCK', '/config/stock_real_01.json', false),
('futures_real_01', '선물 실전 계좌', 'FUTURES', '/config/futures_real_01.json', false),
('stock_virtual_01', '주식 모의 계좌', 'STOCK', '/config/stock_virtual_01.json', true);

INSERT OR IGNORE INTO balances (account_id, total_balance, available_balance) VALUES
('stock_real_01', 10000000, 10000000),
('futures_real_01', 5000000, 5000000),
('stock_virtual_01', 10000000, 10000000);

INSERT OR IGNORE INTO strategies (name, account_id, webhook_token, max_position_ratio) VALUES
('KOSPI_TREND', 'stock_real_01', 'webhook_token_1', 0.15),
('FUTURES_MOMENTUM', 'futures_real_01', 'webhook_token_2', 0.25),
('TEST_STRATEGY', 'stock_virtual_01', 'webhook_token_3', 0.10);