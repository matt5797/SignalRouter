"""
TradingDB - SQLite 기반 거래 데이터 관리
연결 풀링과 트랜잭션 관리를 포함한 데이터베이스 계층
"""

import sqlite3
import threading
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json
from datetime import datetime, date


class TradingDB:
    """SQLite 기반 거래 데이터베이스 관리 클래스"""
    
    def __init__(self, db_path: str = "trading.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_database()
    
    def _init_database(self) -> None:
        """데이터베이스 초기화 및 스키마 생성"""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = f.read()
        
        with self.get_connection() as conn:
            conn.executescript(schema)
    
    def get_connection(self) -> sqlite3.Connection:
        """스레드별 연결 반환 (연결 풀링)"""
        if not hasattr(self._local, 'connection'):
            self._local.connection = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,
                timeout=30.0
            )
            self._local.connection.row_factory = sqlite3.Row
            self._local.connection.execute("PRAGMA foreign_keys = ON")
        return self._local.connection
    
    @contextmanager
    def transaction(self):
        """트랜잭션 컨텍스트 매니저"""
        conn = self.get_connection()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def save_trade(self, trade_data: Dict) -> int:
        """거래 정보 저장"""
        query = """
        INSERT INTO trades (
            account_id, strategy_id, symbol, action, transition_type,
            quantity, price, signal_data, signal_time
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            trade_data['account_id'],
            trade_data['strategy_id'], 
            trade_data['symbol'],
            trade_data['action'],
            trade_data['transition_type'],
            trade_data['quantity'],
            trade_data.get('price'),
            json.dumps(trade_data.get('signal_data', {})),
            trade_data.get('signal_time', datetime.now())
        )
        return self.execute_query(query, params, fetch='lastrowid')
    
    def update_trade_status(self, trade_id: int, status: str, fill_data: Dict) -> None:
        """거래 상태 업데이트"""
        query = """
        UPDATE trades SET 
            status = ?, filled_quantity = ?, avg_fill_price = ?,
            commission = ?, broker_order_id = ?, fill_time = ?
        WHERE id = ?
        """
        params = (
            status,
            fill_data.get('filled_quantity', 0),
            fill_data.get('avg_fill_price'),
            fill_data.get('commission', 0),
            fill_data.get('broker_order_id'),
            fill_data.get('fill_time', datetime.now()),
            trade_id
        )
        self.execute_query(query, params)
    
    def get_position(self, account_id: str, symbol: str) -> Dict:
        """포지션 조회"""
        query = "SELECT * FROM positions WHERE account_id = ? AND symbol = ?"
        result = self.execute_query(query, (account_id, symbol), fetch='one')
        if result:
            return dict(result)
        return {'account_id': account_id, 'symbol': symbol, 'quantity': 0, 'avg_price': 0}
    
    def update_position(self, account_id: str, symbol: str, quantity: int, price: float) -> None:
        """포지션 업데이트"""
        query = """
        INSERT OR REPLACE INTO positions (account_id, symbol, quantity, avg_price, last_updated)
        VALUES (?, ?, ?, ?, ?)
        """
        params = (account_id, symbol, quantity, price, datetime.now())
        self.execute_query(query, params)
    
    def get_strategy_config(self, strategy_name: str) -> Dict:
        """전략 설정 조회"""
        query = "SELECT * FROM strategies WHERE name = ? AND is_active = 1"
        result = self.execute_query(query, (strategy_name,), fetch='one')
        return dict(result) if result else {}
    
    def get_account_trades(self, account_id: str, limit: int = 100) -> List[Dict]:
        """계좌별 거래 내역 조회"""
        query = """
        SELECT * FROM trades WHERE account_id = ?
        ORDER BY signal_time DESC LIMIT ?
        """
        results = self.execute_query(query, (account_id, limit), fetch='all')
        return [dict(row) for row in results] if results else []
    
    def get_daily_pnl(self, account_id: str, target_date: date = None) -> float:
        """일일 손익 계산"""
        if target_date is None:
            target_date = date.today()
        
        query = """
        SELECT
            SUM(CASE WHEN action = 'SELL' THEN filled_quantity * avg_fill_price ELSE 0 END) as sell_amount,
            SUM(CASE WHEN action = 'BUY' THEN filled_quantity * avg_fill_price ELSE 0 END) as buy_amount
        FROM trades
        WHERE account_id = ? AND status = 'FILLED' AND DATE(fill_time) = ?
        """
        result = self.execute_query(query, (account_id, target_date), fetch='one')
        if result and result['sell_amount'] and result['buy_amount']:
            return float(result['sell_amount'] - result['buy_amount'])
        return 0.0
    
    def execute_query(self, query: str, params: Tuple = (), fetch: str = None) -> Any:
        """쿼리 실행 (내부 메서드)"""
        with self.transaction() as conn:
            cursor = conn.execute(query, params)
            
            if fetch == 'one':
                return cursor.fetchone()
            elif fetch == 'all':
                return cursor.fetchall()
            elif fetch == 'lastrowid':
                return cursor.lastrowid
            return cursor.rowcount
    
    def get_all_positions(self, account_id: str) -> List[Dict]:
        """계좌의 모든 포지션 조회 (quantity != 0)"""
        query = "SELECT * FROM positions WHERE account_id = ? AND quantity != 0"
        results = self.execute_query(query, (account_id,), fetch='all')
        return [dict(row) for row in results] if results else []
    
    def get_strategy_by_token(self, webhook_token: str) -> Dict:
        """웹훅 토큰으로 전략 조회"""
        query = "SELECT * FROM strategies WHERE webhook_token = ? AND is_active = 1"
        result = self.execute_query(query, (webhook_token,), fetch='one')
        return dict(result) if result else {}
    
    def close(self) -> None:
        """연결 종료"""
        if hasattr(self._local, 'connection'):
            self._local.connection.close()
            delattr(self._local, 'connection')