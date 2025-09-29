from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Signal:
    symbol: str
    action: str
    quantity: int
    webhook_token: str
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
        
        self.symbol = self.symbol.strip().upper()
        self.action = self.action.strip().upper()
        self.webhook_token = self.webhook_token.strip()
    
    def validate(self) -> tuple[bool, Optional[str]]:
        if not self.symbol:
            return False, "Symbol is required"
        
        if self.action not in ['BUY', 'SELL']:
            return False, f"Invalid action: {self.action}"
        
        if self.quantity <= 0:
            return False, f"Invalid quantity: {self.quantity}"
        
        if not self.webhook_token:
            return False, "Webhook token is required"
        
        return True, None
    
    @classmethod
    def from_webhook(cls, payload: dict) -> 'Signal':
        return cls(
            symbol=payload.get('symbol', ''),
            action=payload.get('action', ''),
            quantity=int(payload.get('quantity', 0)),
            webhook_token=payload.get('webhook_token', '')
        )
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'action': self.action,
            'quantity': self.quantity,
            'webhook_token': self.webhook_token,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class ExecutionResult:
    success: bool
    order_id: Optional[str] = None
    error: Optional[str] = None
    signal: Optional[Signal] = None
    filled: bool = False
    
    @classmethod
    def ok(cls, order_id: str, signal: Signal = None, filled: bool = True) -> 'ExecutionResult':
        return cls(success=True, order_id=order_id, signal=signal, filled=filled)
    
    @classmethod
    def fail(cls, error: str, signal: Signal = None, order_id: str = None) -> 'ExecutionResult':
        return cls(success=False, error=error, signal=signal, order_id=order_id)
    
    def to_dict(self) -> dict:
        result = {
            'success': self.success,
            'order_id': self.order_id,
            'error': self.error,
            'filled': self.filled
        }
        if self.signal:
            result['signal'] = self.signal.to_dict()
        return result