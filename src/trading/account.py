"""
Account - 계좌별 관리 클래스
브로커 API를 통한 계좌 특화 기능 제공
"""

from typing import Dict, List, Optional
from enum import Enum
import logging
from .kis_broker import KisBroker

logger = logging.getLogger(__name__)


class AccountType(Enum):
    """계좌 유형"""
    STOCK = "STOCK"
    FUTURES = "FUTURES"


class Account:
    """계좌 관리 클래스"""
    
    def __init__(
        self, 
        account_id: str, 
        name: str, 
        account_type: AccountType,
        secret_file_path: str,
        is_virtual: bool = False,
        is_active: bool = True,
    ):
        self.account_id = account_id
        self.name = name
        self.account_type = AccountType(account_type) if isinstance(account_type, str) else account_type
        self.is_virtual = is_virtual
        self.is_active = is_active
        
        # Broker 인스턴스 생성 (모의투자인 경우 default_real_secret 전달)
        self.broker = KisBroker(
            account_id=account_id, 
            secret_file_path=secret_file_path, 
            is_virtual=is_virtual
        )
        
        # 캐시된 잔고 정보
        self._cached_balance = None
        self._cached_positions = None
        
        logger.info(f"Account initialized: {account_id} ({name}) - Virtual: {is_virtual}")
    
    def get_balance(self) -> Dict:
        """계좌 잔고 조회"""
        if not self.is_active:
            logger.warning(f"Account {self.account_id} is inactive")
            return {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
        
        try:
            balance = self.broker.get_balance()
            self._cached_balance = balance
            return balance
        except Exception as e:
            logger.error(f"Failed to get balance for {self.account_id}: {e}")
            return self._cached_balance or {'total_balance': 0.0, 'available_balance': 0.0, 'currency': 'KRW'}
    
    def get_positions(self) -> List[Dict]:
        """보유 포지션 조회"""
        if not self.is_active:
            logger.warning(f"Account {self.account_id} is inactive")
            return []
        
        try:
            positions = self.broker.get_positions()
            self._cached_positions = positions
            return positions
        except Exception as e:
            logger.error(f"Failed to get positions for {self.account_id}: {e}")
            return self._cached_positions or []
    
    def can_trade(self, amount: float) -> bool:
        """거래 가능 여부 확인"""
        if not self.is_active:
            return False
        
        try:
            balance = self.get_balance()
            available = balance.get('available_balance', 0.0)
            return available >= amount
        except Exception as e:
            logger.error(f"Failed to check trading capability: {e}")
            return False
    
    def sync_balance(self) -> None:
        """잔고 정보 동기화 (캐시 갱신)"""
        try:
            self._cached_balance = self.broker.get_balance()
            self._cached_positions = self.broker.get_positions()
            logger.info(f"Balance synced for account {self.account_id}")
        except Exception as e:
            logger.error(f"Failed to sync balance for {self.account_id}: {e}")
    
    def get_position_for_symbol(self, symbol: str) -> Dict:
        """특정 종목의 포지션 조회"""
        positions = self.get_positions()
        for position in positions:
            if position['symbol'] == symbol:
                return position
        
        # 포지션이 없으면 빈 포지션 반환
        return {
            'symbol': symbol,
            'quantity': 0,
            'avg_price': 0.0,
            'current_value': 0.0,
            'unrealized_pnl': 0.0
        }
    
    def get_orderable_amount(self, symbol: str, price: float = None) -> Dict:
        """매수 가능 금액/수량 조회"""
        if not self.is_active:
            return {'symbol': symbol, 'orderable_quantity': 0, 'orderable_amount': 0.0, 'unit_price': 0.0}
        
        try:
            return self.broker.get_orderable_amount(symbol, price)
        except Exception as e:
            logger.error(f"Failed to get orderable amount: {e}")
            return {'symbol': symbol, 'orderable_quantity': 0, 'orderable_amount': 0.0, 'unit_price': 0.0}

    def get_total_portfolio_value(self) -> float:
        """총 포트폴리오 가치"""
        try:
            balance = self.get_balance()
            positions = self.get_positions()
            
            cash_value = balance.get('total_balance', 0.0)
            position_value = sum(pos.get('current_value', 0.0) for pos in positions)
            
            return cash_value + position_value
        except Exception as e:
            logger.error(f"Failed to calculate portfolio value: {e}")
            return 0.0
    
    def get_total_unrealized_pnl(self) -> float:
        """총 미실현 손익"""
        try:
            positions = self.get_positions()
            return sum(pos.get('unrealized_pnl', 0.0) for pos in positions)
        except Exception as e:
            logger.error(f"Failed to calculate unrealized PnL: {e}")
            return 0.0
    
    def is_stock_account(self) -> bool:
        """주식 계좌 여부"""
        return self.account_type == AccountType.STOCK
    
    def is_futures_account(self) -> bool:
        """선물 계좌 여부"""
        return self.account_type == AccountType.FUTURES
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            'account_id': self.account_id,
            'name': self.name,
            'account_type': self.account_type.value,
            'is_virtual': self.is_virtual,
            'is_active': self.is_active,
            'balance': self._cached_balance,
            'positions_count': len(self._cached_positions or [])
        }