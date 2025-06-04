"""
TradeOrder - 거래 주문 데이터 모델
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional


class TransitionType(Enum):
    """포지션 전환 타입"""
    ENTRY = "ENTRY"      # 신규 진입
    EXIT = "EXIT"        # 포지션 종료
    REVERSE = "REVERSE"  # 포지션 방향 전환


class TradeStatus(Enum):
    """거래 상태"""
    SIGNAL = "SIGNAL"    # 시그널 수신
    PENDING = "PENDING"  # 주문 대기
    FILLED = "FILLED"    # 체결 완료
    FAILED = "FAILED"    # 주문 실패


@dataclass
class TradeOrder:
    """거래 주문 데이터 클래스"""
    
    account_id: str              # 계좌 ID
    symbol: str                  # 종목 코드
    action: str                  # BUY/SELL
    quantity: int                # 수량
    price: Optional[float]       # 가격 (None=시장가)
    transition_type: TransitionType  # 포지션 전환 타입
    
    def __post_init__(self):
        """초기화 후 처리"""
        # 액션 정규화
        self.action = self.action.upper()
        
        # 유효성 검증
        if self.action not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid action: {self.action}")
        
        if self.quantity <= 0:
            raise ValueError(f"Invalid quantity: {self.quantity}")
        
        if isinstance(self.transition_type, str):
            self.transition_type = TransitionType(self.transition_type)
    
    def is_market_order(self) -> bool:
        """시장가 주문 여부"""
        return self.price is None
    
    def is_limit_order(self) -> bool:
        """지정가 주문 여부"""
        return self.price is not None
    
    def is_buy_order(self) -> bool:
        """매수 주문 여부"""
        return self.action == 'BUY'
    
    def is_sell_order(self) -> bool:
        """매도 주문 여부"""
        return self.action == 'SELL'
    
    def to_broker_format(self) -> Dict:
        """브로커 API 호출용 포맷으로 변환"""
        return {
            'symbol': self.symbol,
            'action': self.action,
            'quantity': self.quantity,
            'price': self.price,
            'order_type': 'MARKET' if self.is_market_order() else 'LIMIT'
        }
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            'account_id': self.account_id,
            'symbol': self.symbol,
            'action': self.action,
            'quantity': self.quantity,
            'price': self.price,
            'transition_type': self.transition_type.value,
            'order_type': 'MARKET' if self.is_market_order() else 'LIMIT'
        }
    
    def get_estimated_value(self) -> float:
        """예상 거래 금액"""
        if self.price is None:
            return 0.0  # 시장가는 예상 불가
        return self.quantity * self.price
    
    @classmethod
    def from_signal(cls, signal_data: Dict, account_id: str, transition_type: TransitionType) -> 'TradeOrder':
        """시그널 데이터에서 주문 생성"""
        return cls(
            account_id=account_id,
            symbol=signal_data['symbol'],
            action=signal_data['action'],
            quantity=signal_data['quantity'],
            price=signal_data.get('price'),
            transition_type=transition_type
        )