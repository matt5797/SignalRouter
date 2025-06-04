"""
Position - 포지션 데이터 모델
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict


@dataclass
class Position:
    """포지션 데이터 클래스"""
    
    account_id: str        # 계좌 ID
    symbol: str           # 종목 코드
    quantity: int         # 수량 (양수=롱, 음수=숏, 0=포지션없음)
    avg_price: float      # 평균 단가
    last_updated: datetime = None
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.last_updated is None:
            self.last_updated = datetime.now()
    
    def is_flat(self) -> bool:
        """포지션 없음 (수량 0) 여부"""
        return self.quantity == 0
    
    def is_long(self) -> bool:
        """롱 포지션 여부"""
        return self.quantity > 0
    
    def is_short(self) -> bool:
        """숏 포지션 여부"""
        return self.quantity < 0
    
    def get_market_value(self, current_price: float) -> float:
        """현재가 기준 시장 가치"""
        return abs(self.quantity) * current_price
    
    def get_unrealized_pnl(self, current_price: float) -> float:
        """미실현 손익 계산"""
        if self.is_flat():
            return 0.0
        
        if self.is_long():
            return self.quantity * (current_price - self.avg_price)
        else:  # short position
            return abs(self.quantity) * (self.avg_price - current_price)
    
    def get_unrealized_pnl_rate(self, current_price: float) -> float:
        """미실현 손익률 계산 (%)"""
        if self.is_flat() or self.avg_price == 0:
            return 0.0
        
        pnl = self.get_unrealized_pnl(current_price)
        cost_basis = abs(self.quantity) * self.avg_price
        
        return (pnl / cost_basis) * 100
    
    def can_add_quantity(self, quantity: int) -> bool:
        """수량 추가 가능 여부 (동일 방향)"""
        if self.is_flat():
            return True
        
        # 기존 포지션과 같은 방향인지 확인
        return (self.quantity > 0 and quantity > 0) or (self.quantity < 0 and quantity < 0)
    
    def would_reverse_position(self, quantity: int) -> bool:
        """포지션 방향 전환 여부"""
        if self.is_flat():
            return False
        
        new_quantity = self.quantity + quantity
        return (self.quantity > 0 and new_quantity < 0) or (self.quantity < 0 and new_quantity > 0)
    
    def calculate_new_avg_price(self, add_quantity: int, add_price: float) -> float:
        """새로운 평균 단가 계산"""
        if self.is_flat():
            return add_price
        
        if not self.can_add_quantity(add_quantity):
            return add_price  # 방향이 다르면 새 가격 적용
        
        total_cost = (abs(self.quantity) * self.avg_price) + (abs(add_quantity) * add_price)
        total_quantity = abs(self.quantity) + abs(add_quantity)
        
        return total_cost / total_quantity if total_quantity > 0 else 0.0
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            'account_id': self.account_id,
            'symbol': self.symbol,
            'quantity': self.quantity,
            'avg_price': self.avg_price,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'position_type': 'LONG' if self.is_long() else 'SHORT' if self.is_short() else 'FLAT'
        }