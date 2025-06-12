-- SignalRouter 자동매매 시스템 PostgreSQL 스키마

-- 계좌 관리
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    account_type TEXT NOT NULL CHECK (account_type IN ('STOCK', 'FUTURES')),
    secret_file_path TEXT NOT NULL,
    is_virtual BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 계좌별 잔고
CREATE TABLE IF NOT EXISTS balances (
    account_id TEXT PRIMARY KEY,
    total_balance NUMERIC(15,2) NOT NULL DEFAULT 0,
    available_balance NUMERIC(15,2) NOT NULL DEFAULT 0,
    unrealized_pnl NUMERIC(15,2) NOT NULL DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

-- 전략 설정
CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    webhook_token TEXT NOT NULL UNIQUE,
    max_position_ratio NUMERIC(5,4) NOT NULL DEFAULT 0.2,
    max_daily_loss NUMERIC(15,2) NOT NULL DEFAULT 500000,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

-- 거래 내역
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    account_id TEXT NOT NULL,
    strategy_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('BUY', 'SELL')),
    transition_type TEXT NOT NULL CHECK (transition_type IN ('ENTRY', 'EXIT', 'REVERSE')),
    quantity INTEGER NOT NULL,
    price NUMERIC(10,2),
    filled_quantity INTEGER DEFAULT 0,
    avg_fill_price NUMERIC(10,2),
    commission NUMERIC(10,2) DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'SIGNAL' CHECK (status IN ('SIGNAL', 'PENDING', 'FILLED', 'FAILED')),
    broker_order_id TEXT,
    signal_data TEXT,
    signal_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fill_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts(account_id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- 포지션 관리
CREATE TABLE IF NOT EXISTS positions (
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_price NUMERIC(10,2) NOT NULL DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_id, symbol),
    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
);

-- 성능 인덱스
CREATE INDEX IF NOT EXISTS idx_trades_account_symbol ON trades(account_id, symbol);
CREATE INDEX IF NOT EXISTS idx_trades_strategy_time ON trades(strategy_id, signal_time);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_strategies_webhook ON strategies(webhook_token);

-- 포지션 자동 업데이트 함수
CREATE OR REPLACE FUNCTION update_position_after_fill()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'FILLED' AND OLD.status != 'FILLED' THEN
        INSERT INTO positions (account_id, symbol, quantity, avg_price, last_updated)
        VALUES (
            NEW.account_id,
            NEW.symbol,
            COALESCE((SELECT quantity FROM positions WHERE account_id = NEW.account_id AND symbol = NEW.symbol), 0) +
            CASE WHEN NEW.action = 'BUY' THEN NEW.filled_quantity ELSE -NEW.filled_quantity END,
            NEW.avg_fill_price,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (account_id, symbol) 
        DO UPDATE SET 
            quantity = EXCLUDED.quantity,
            avg_price = EXCLUDED.avg_price,
            last_updated = EXCLUDED.last_updated;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 트리거 생성
DROP TRIGGER IF EXISTS trigger_update_position_after_fill ON trades;
CREATE TRIGGER trigger_update_position_after_fill
    AFTER UPDATE ON trades
    FOR EACH ROW
    EXECUTE FUNCTION update_position_after_fill();
