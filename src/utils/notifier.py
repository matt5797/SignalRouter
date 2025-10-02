import logging
from typing import Optional
from ..models.signal import Signal, ExecutionResult

logger = logging.getLogger(__name__)


class Notifier:
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.enabled = self.config.get('enabled', False)
        
        if self.enabled:
            logger.info("Notifier enabled")
        else:
            logger.info("Notifier disabled")
    
    def notify_order_failed(self, signal: Signal, error: str, order_id: str = None):
        if not self.enabled:
            return
        
        message = f"Order Failed: {signal.symbol} {signal.action} x{signal.quantity}\nError: {error}"
        if order_id:
            message += f"\nOrder ID: {order_id}"
        
        logger.warning(f"[NOTIFY] {message}")
    
    def notify_fill_timeout(self, signal: Signal, order_id: str):
        if not self.enabled:
            return
        
        message = f"Fill Timeout: {signal.symbol} {signal.action} x{signal.quantity}\nOrder ID: {order_id}"
        logger.warning(f"[NOTIFY] {message}")
    
    def notify_emergency_stop(self):
        if not self.enabled:
            return
        
        message = "EMERGENCY STOP ACTIVATED - All trading halted"
        logger.critical(f"[NOTIFY] {message}")
    
    def notify_execution_result(self, result: ExecutionResult):
        if not self.enabled:
            return
        
        if not result.success:
            self.notify_order_failed(result.signal, result.error, result.order_id)
        elif not result.filled:
            self.notify_fill_timeout(result.signal, result.order_id)