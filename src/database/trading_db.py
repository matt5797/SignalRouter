"""
TradingDB - PostgreSQL 기반 거래 데이터 관리
연결 풀링과 트랜잭션 관리를 포함한 데이터베이스 계층
"""

import os
import threading
import psycopg2
import psycopg2.pool
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


class TradingDB:
    """PostgreSQL 기반 거래 데이터베이스 관리 클래스"""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.db_url = self._get_database_url()
        self.is_postgresql = self.db_url.startswith(('postgresql://', 'postgres://'))
        
        if self.is_postgresql:
            self._init_postgresql()
        else:
            self._init_sqlite()
        
        self._init_database()
    
    def _get_database_url(self) -> str:
        """데이터베이스 URL 결정 (환경변수 우선)"""
        # Railway에서 제공하는 환경변수들 확인
        db_url = (
            os.getenv('DATABASE_URL') or 
            os.getenv('POSTGRESQL_URL') or 
            os.getenv('POSTGRES_URL') or
            self.config.get('postgresql_url', '')
        )
        
        if db_url:
            # postgres:// -> postgresql:// 변환 (psycopg2 호환성)
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
            return db_url
        
        # 기본값: SQLite (로컬 개발용)
        return self.config.get('path', 'data/trading.db')
    
    def _init_postgresql(self):
        """PostgreSQL 연결 풀 초기화"""
        try:
            pool_size = self.config.get('pool_size', 5)
            max_overflow = self.config.get('max_overflow', 10)
            
            self._pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=pool_size + max_overflow,
                dsn=self.db_url
            )
            self._local = threading.local()
            logger.info("PostgreSQL connection pool initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise
    
    def _init_sqlite(self):
        """SQLite 초기화 (fallback)"""
        import sqlite3
        self.db_path = self.db_url
        self._local = threading.local()
        logger.info(f"SQLite database: {self.db_path}")
    
    def _init_database(self) -> None:
        """데이터베이스 스키마 초기화"""
        schema_path = Path(__file__).parent / "schema.sql"
        
        if not schema_path.exists():
            logger.warning("Schema file not found, skipping initialization")
            return
        
        try:
            with open(schema_path, 'r', encoding='utf-8') as f:
                schema = f.read()
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(schema)
                conn.commit()
                
            logger.info("Database schema initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize database schema: {e}")
            # 스키마 초기화 실패는 치명적이지 않을 수 있음
    
    def get_connection(self):
        """연결 반환 (PostgreSQL 풀 또는 SQLite)"""
        if self.is_postgresql:
            return self._get_postgresql_connection()
        else:
            return self._get_sqlite_connection()
    
    def _get_postgresql_connection(self):
        """PostgreSQL 연결 반환"""
        if not hasattr(self._local, 'connection') or self._local.connection.closed:
            self._local.connection = self._pool.getconn()
            self._local.connection.autocommit = False
        return self._local.connection
    
    def _get_sqlite_connection(self):
        """SQLite 연결 반환 (기존 로직)"""
        import sqlite3
        
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
            if self.is_postgresql:
                # PostgreSQL: 명시적 트랜잭션
                with conn.cursor() as cursor:
                    cursor.execute("BEGIN")
                yield conn
                conn.commit()
            else:
                # SQLite: 기존 로직
                conn.execute("BEGIN")
                yield conn
                conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    def save_trade(self, trade_data: Dict) -> int:
        """거래 정보 저장"""
        if self.is_postgresql:
            query = """
            INSERT INTO trades (
                account_id, strategy_id, symbol, action, transition_type,
                quantity, price, signal_data, signal_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
        else:
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
        
        if self.is_postgresql:
            return self.execute_query(query, params, fetch='one')[0]
        else:
            return self.execute_query(query, params, fetch='lastrowid')
    
    def update_trade_status(self, trade_id: int, status: str, fill_data: Dict) -> None:
        """거래 상태 업데이트"""
        placeholder = "%s" if self.is_postgresql else "?"
        
        query = f"""
        UPDATE trades SET 
            status = {placeholder}, filled_quantity = {placeholder}, avg_fill_price = {placeholder},
            commission = {placeholder}, broker_order_id = {placeholder}, fill_time = {placeholder}
        WHERE id = {placeholder}
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
        placeholder = "%s" if self.is_postgresql else "?"
        query = f"SELECT * FROM positions WHERE account_id = {placeholder} AND symbol = {placeholder}"
        
        result = self.execute_query(query, (account_id, symbol), fetch='one')
        if result:
            return dict(result)
        return {'account_id': account_id, 'symbol': symbol, 'quantity': 0, 'avg_price': 0}
    
    def update_position(self, account_id: str, symbol: str, quantity: int, price: float) -> None:
        """포지션 업데이트"""
        if self.is_postgresql:
            query = """
            INSERT INTO positions (account_id, symbol, quantity, avg_price, last_updated)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (account_id, symbol) 
            DO UPDATE SET 
                quantity = EXCLUDED.quantity,
                avg_price = EXCLUDED.avg_price,
                last_updated = EXCLUDED.last_updated
            """
        else:
            query = """
            INSERT OR REPLACE INTO positions (account_id, symbol, quantity, avg_price, last_updated)
            VALUES (?, ?, ?, ?, ?)
            """
        
        params = (account_id, symbol, quantity, price, datetime.now())
        self.execute_query(query, params)
    
    def get_strategy_config(self, strategy_name: str) -> Dict:
        """전략 설정 조회"""
        placeholder = "%s" if self.is_postgresql else "?"
        query = f"SELECT * FROM strategies WHERE name = {placeholder} AND is_active = true"
        
        result = self.execute_query(query, (strategy_name,), fetch='one')
        return dict(result) if result else {}
    
    def get_account_trades(self, account_id: str, limit: int = 100) -> List[Dict]:
        """계좌별 거래 내역 조회"""
        placeholder = "%s" if self.is_postgresql else "?"
        query = f"""
        SELECT * FROM trades WHERE account_id = {placeholder}
        ORDER BY signal_time DESC LIMIT {placeholder}
        """
        
        results = self.execute_query(query, (account_id, limit), fetch='all')
        return [dict(row) for row in results] if results else []
    
    def get_daily_pnl(self, account_id: str, target_date: date = None) -> float:
        """일일 손익 계산"""
        if target_date is None:
            target_date = date.today()
        
        placeholder = "%s" if self.is_postgresql else "?"
        
        if self.is_postgresql:
            date_condition = f"DATE(fill_time) = {placeholder}"
        else:
            date_condition = f"DATE(fill_time) = {placeholder}"
        
        query = f"""
        SELECT
            SUM(CASE WHEN action = 'SELL' THEN filled_quantity * avg_fill_price ELSE 0 END) as sell_amount,
            SUM(CASE WHEN action = 'BUY' THEN filled_quantity * avg_fill_price ELSE 0 END) as buy_amount
        FROM trades
        WHERE account_id = {placeholder} AND status = 'FILLED' AND {date_condition}
        """
        
        result = self.execute_query(query, (account_id, target_date), fetch='one')
        if result and result[0] and result[1]:
            return float(result[0] - result[1])
        return 0.0
    
    def execute_query(self, query: str, params: Tuple = (), fetch: str = None) -> Any:
        """쿼리 실행"""
        with self.transaction() as conn:
            if self.is_postgresql:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    
                    if fetch == 'one':
                        return cursor.fetchone()
                    elif fetch == 'all':
                        return cursor.fetchall()
                    elif fetch == 'lastrowid':
                        return cursor.lastrowid if hasattr(cursor, 'lastrowid') else None
                    return cursor.rowcount
            else:
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
        placeholder = "%s" if self.is_postgresql else "?"
        query = f"SELECT * FROM positions WHERE account_id = {placeholder} AND quantity != 0"
        
        results = self.execute_query(query, (account_id,), fetch='all')
        return [dict(row) for row in results] if results else []
    
    def get_strategy_by_token(self, webhook_token: str) -> Dict:
        """웹훅 토큰으로 전략 조회"""
        placeholder = "%s" if self.is_postgresql else "?"
        query = f"SELECT * FROM strategies WHERE webhook_token = {placeholder} AND is_active = true"
        
        result = self.execute_query(query, (webhook_token,), fetch='one')
        return dict(result) if result else {}
    
    def close(self) -> None:
        """연결 종료"""
        try:
            if self.is_postgresql:
                if hasattr(self._local, 'connection'):
                    self._pool.putconn(self._local.connection)
                    delattr(self._local, 'connection')
                self._pool.closeall()
            else:
                if hasattr(self._local, 'connection'):
                    self._local.connection.close()
                    delattr(self._local, 'connection')
            logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database connections: {e}")
    
    def get_connection_info(self) -> Dict:
        """연결 정보 반환 (디버깅용)"""
        return {
            'database_type': 'postgresql' if self.is_postgresql else 'sqlite',
            'database_url': self.db_url if self.is_postgresql else self.db_path,
            'config': self.config
        }