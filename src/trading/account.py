"""
Account - 계좌별 관리 클래스
브로커 API를 통한 계좌 특화 기능 제공
"""

from typing import Dict, List, Optional
from enum import Enum
import logging
from datetime import datetime
from .kis_broker import KisBroker
from .exceptions import AccountError

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
        token_storage_path: str = "secrets/tokens/"
    ):
        self.account_id = account_id
        self.name = name
        self.account_type = AccountType(account_type) if isinstance(account_type, str) else account_type
        self.is_virtual = is_virtual
        self.is_active = is_active
        
        # Broker 인스턴스 생성
        self.broker = KisBroker(
            account_id=account_id, 
            secret_file_path=secret_file_path, 
            is_virtual=is_virtual,
            token_storage_path=token_storage_path
        )
        
        logger.info(f"Account initialized: {account_id} ({name}) - Virtual: {is_virtual}")
    
    # ========== 조회 메서드 ==========
    
    def get_balance(self) -> Dict:
        """계좌 잔고 조회"""
        if not self.is_active:
            raise AccountError(f"Account {self.account_id} is inactive")
        
        # 신뢰성 정보 추가
        return self.broker.get_balance()
    
    def get_positions(self) -> List[Dict]:
        """보유 포지션 조회"""
        if not self.is_active:
            raise AccountError(f"Account {self.account_id} is inactive")
        
        return self.broker.get_positions()
    
    def get_position_for_symbol(self, symbol: str) -> Dict:
        """특정 종목의 포지션 조회"""
        positions = self.get_positions()
        for position in positions:
            if position['symbol'] == symbol:
                return position
        
        return {
            'symbol': symbol,
            'quantity': 0,
            'avg_price': 0.0,
            'current_value': 0.0,
            'unrealized_pnl': 0.0
        }
    
    def get_orderable_amount(self, symbol: str, price: float = None) -> Dict:
        """매수 가능 금액/수량 조회 - 에러시 0 반환"""
        if not self.is_active:
            raise AccountError(f"Account {self.account_id} is inactive")
        
        return self.broker.get_orderable_amount(symbol, price)
    
    # ========== 거래 가능 여부 판단 ==========
    
    def can_trade(self, amount: float) -> Dict:
        """거래 가능 여부 확인"""
        if not self.is_active:
            return False
        
        balance = self.get_balance()

        try:
            balance = self.get_balance()  # 실패하면 예외 발생
            return balance.get('available_balance', 0.0) >= amount
        except Exception as e:
            logger.error(f"Cannot check trade capability: {e}")
            return False
    
    # ========== 포트폴리오 계산 ==========
    
    def get_total_portfolio_value(self) -> Dict:
        """총 포트폴리오 가치"""
        balance = self.get_balance()
        positions = self.get_positions()
        
        cash_value = balance.get('total_balance', 0.0)
        position_value = sum(pos.get('current_value', 0.0) for pos in positions)
        
        return cash_value + position_value
    
    def get_total_unrealized_pnl(self) -> Dict:
        """총 미실현 손익"""
        positions = self.get_positions()
        return sum(pos.get('unrealized_pnl', 0.0) for pos in positions)
    
    # ========== 기존 메서드들 ==========
    
    def is_stock_account(self) -> bool:
        """주식 계좌 여부"""
        return self.account_type == AccountType.STOCK
    
    def is_futures_account(self) -> bool:
        """선물 계좌 여부"""
        return self.account_type == AccountType.FUTURES
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        try:
            balance = self.get_balance()
            positions = self.get_positions()
            
            return {
                'account_id': self.account_id,
                'name': self.name,
                'account_type': self.account_type.value,
                'is_virtual': self.is_virtual,
                'is_active': self.is_active,
                'balance': {
                    'total': balance.get('total_balance', 0.0),
                    'available': balance.get('available_balance', 0.0)
                },
                'positions_count': len(positions)
            }
        except Exception as e:
            logger.error(f"Failed to convert account to dict: {e}")
            return {
                'account_id': self.account_id,
                'name': self.name,
                'account_type': self.account_type.value,
                'is_virtual': self.is_virtual,
                'is_active': self.is_active,
                'balance': {'total': 0.0, 'available': 0.0},
                'positions_count': 0,
                'error': str(e)
            }
