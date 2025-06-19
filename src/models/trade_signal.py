"""
TradeSignal - 트레이딩뷰 시그널 데이터 모델
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, Optional


@dataclass
class TradeSignal:
    """트레이딩 시그널 데이터 클래스"""
    
    strategy: str           # 전략명
    symbol: str            # 종목 코드
    action: str            # BUY/SELL
    quantity: int          # 수량 (0 또는 -1이면 전량 처리)
    price: Optional[float] = None    # 가격 (None=시장가)
    reverse_position: bool = False   # 포지션 전환 플래그
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        """초기화 후 처리"""
        if self.timestamp is None:
            self.timestamp = datetime.now()
        
        # 액션 정규화
        self.action = self.action.upper()
        
        # 기본 검증
        if self.action not in ['BUY', 'SELL']:
            raise ValueError(f"Invalid action: {self.action}")
        
        if self.quantity < -1:
            raise ValueError(f"Invalid quantity: {self.quantity}")
    
    def is_valid(self) -> bool:
        """시그널 유효성 검증"""
        try:
            # 필수 필드 검증
            if not all([self.strategy, self.symbol, self.action]):
                return False
            
            # 액션 유효성
            if self.action not in ['BUY', 'SELL']:
                return False
            
            # 수량 유효성
            if self.quantity < -1:
                return False
            
            # 가격 유효성 (None은 시장가로 허용)
            if self.price is not None and self.price <= 0:
                return False
            
            return True
            
        except Exception:
            return False
    
    def is_reverse_signal(self) -> bool:
        """포지션 전환 시그널 여부"""
        return self.reverse_position
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        data = asdict(self)
        # datetime을 ISO 포맷 문자열로 변환
        if data['timestamp']:
            data['timestamp'] = data['timestamp'].isoformat()
        return data
    
    @classmethod
    def from_webhook_payload(cls, payload: Dict) -> 'TradeSignal':
        """웹훅 페이로드에서 시그널 생성"""
        quantity = payload.get('quantity', 0)
        if quantity is None:
            quantity = 0
        
        reverse_position = payload.get('reverse_position', False)
        if isinstance(reverse_position, str):
            reverse_position = reverse_position.lower() in ['true', '1', 'yes']
        
        return cls(
            strategy=payload.get('strategy', ''),
            symbol=payload.get('symbol', ''),
            action=payload.get('action', ''),
            quantity=int(quantity),
            price=float(payload['price']) if payload.get('price') else None,
            reverse_position=reverse_position,
            timestamp=datetime.now()
        )
    
    def is_market_order(self) -> bool:
        """시장가 주문 여부"""
        return self.price is None
    
    def is_limit_order(self) -> bool:
        """지정가 주문 여부"""
        return self.price is not None
    
    def get_order_type(self) -> str:
        """주문 유형 반환"""
        return "MARKET" if self.is_market_order() else "LIMIT"