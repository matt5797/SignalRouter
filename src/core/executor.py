import time
import logging
from typing import Dict, Optional
from pathlib import Path

from ..models.signal import Signal, ExecutionResult
from ..broker.kis_api import KisBroker
from ..config.loader import ConfigLoader

logger = logging.getLogger(__name__)


class SignalExecutor:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = ConfigLoader(config_path)
        self.brokers: Dict[str, KisBroker] = {}
        self._emergency_stop = False
        
        logger.info("SignalExecutor initialized")
    
    def execute(self, signal: Signal) -> ExecutionResult:
        if self._emergency_stop:
            logger.warning("Emergency stop active, signal ignored")
            return ExecutionResult.fail("Emergency stop is active", signal)
        
        valid, error = signal.validate()
        if not valid:
            logger.error(f"Invalid signal: {error}")
            return ExecutionResult.fail(f"Invalid signal: {error}", signal)
        
        account_config = self._route_signal(signal)
        if not account_config:
            logger.error(f"Account not found for token: {signal.webhook_token}")
            return ExecutionResult.fail("Account not found", signal)
        
        if not account_config.get('is_active', False):
            logger.warning(f"Account {account_config['account_id']} is inactive")
            return ExecutionResult.fail("Account is inactive", signal)
        
        broker = self._get_broker(account_config)
        
        try:
            logger.info(f"Executing signal: {signal.action} {signal.symbol} x{signal.quantity}")
            
            if signal.action == 'BUY':
                order_id = broker.buy(signal.symbol, signal.quantity, price=None)
            else:
                order_id = broker.sell(signal.symbol, signal.quantity, price=None)
            
            logger.info(f"Order placed: {order_id}")
            
            filled = self._wait_for_fill(broker, order_id, timeout=30)
            
            if filled:
                logger.info(f"Order filled: {order_id}")
                return ExecutionResult.ok(order_id, signal, filled=True)
            else:
                logger.warning(f"Order fill timeout: {order_id}")
                return ExecutionResult.fail("Fill timeout", signal, order_id)
        
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            return ExecutionResult.fail(str(e), signal)
    
    def _route_signal(self, signal: Signal) -> Optional[dict]:
        strategy = self.config.get_strategy_by_token(signal.webhook_token)
        if not strategy:
            return None
        
        if not strategy.get('is_active', False):
            return None
        
        account_id = strategy['account_id']
        return self.config.get_account(account_id)
    
    def _get_broker(self, account_config: dict) -> KisBroker:
        account_id = account_config['account_id']
        
        if account_id not in self.brokers:
            token_path = self.config.get_token_storage_path()
            
            secret_identifier = account_config.get('secret_file', account_id)
            
            self.brokers[account_id] = KisBroker(
                account_id=account_id,
                secret_identifier=secret_identifier,
                is_virtual=account_config.get('is_virtual', False),
                token_storage_path=token_path
            )
            
            logger.info(f"Broker created for account: {account_id} (secret: {secret_identifier})")
        
        return self.brokers[account_id]
    
    def _wait_for_fill(self, broker: KisBroker, order_id: str, timeout: int = 30) -> bool:
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                status_result = broker.get_order_status(order_id)
                status_data = status_result.get('data', {})
                status = status_data.get('status', 'UNKNOWN')
                
                if status == 'FILLED':
                    return True
                elif status in ['FAILED', 'REJECTED', 'CANCELLED']:
                    logger.error(f"Order failed with status: {status}")
                    return False
                
                time.sleep(2)
            
            except Exception as e:
                logger.warning(f"Status check error: {e}")
                time.sleep(2)
        
        return False
    
    def emergency_stop(self):
        self._emergency_stop = True
        logger.critical("EMERGENCY STOP ACTIVATED")
    
    def resume(self):
        self._emergency_stop = False
        logger.info("Trading resumed")
    
    def is_stopped(self) -> bool:
        return self._emergency_stop
    
    def get_status(self) -> dict:
        return {
            'emergency_stop': self._emergency_stop,
            'active_brokers': len(self.brokers),
            'broker_accounts': list(self.brokers.keys())
        }