"""
TradeExecutor - 주문 실행 및 리스크 관리 클래스
시그널 기반 주문 실행과 기본적인 리스크 체크 제공
"""

import time
from typing import Dict, Optional, Tuple
from datetime import datetime, date
import logging
from ..database import TradingDB
from ..config import ConfigLoader
from ..models import TradeOrder, TransitionType, TradeStatus
from .account import Account, AccountType
from .exceptions import TradingError, AccountError, RiskManagementError

logger = logging.getLogger(__name__)


class TradeExecutor:
    """주문 실행 및 리스크 관리 클래스"""
    
    def __init__(self, db: TradingDB, config: ConfigLoader = None):
        self.db = db
        self.config = config
        logger.info("TradeExecutor initialized")
    
    # ========== 메인 실행 로직 ==========

    def execute_signal(self, account: Account, signal_data: Dict) -> Dict:
        """
        시그널 실행 메인 로직
        
        Returns:
            Dict: {
                'success': bool,
                'trade_id': int,
                'order_id': str,
                'message': str,
                'error_type': str,  # 'validation', 'risk', 'broker', 'system'
                'details': dict
            }
        """
        try:
            # 1. 전략 설정 조회
            if not self.config:
                return self._error_result(
                    'system', 
                    "ConfigLoader not available for strategy lookup"
                )
            
            strategy_config = self.config.get_strategy_by_token(signal_data.get('webhook_token', ''))
            if not strategy_config:
                return self._error_result(
                    'validation', 
                    f"Strategy not found for token: {signal_data.get('webhook_token')}"
                )
            
            # 2. 심볼 변환 (선물인 경우)
            original_symbol = signal_data.get('symbol', '')
            converted_symbol = original_symbol
            
            if account.account_type == AccountType.FUTURES:
                converted_symbol = account.broker.convert_symbol_to_futures_code(original_symbol)
                if converted_symbol != original_symbol:
                    logger.info(f"Futures symbol converted: {original_symbol} -> {converted_symbol}")
            
            # 시그널 데이터에 변환된 심볼 적용
            signal_data = signal_data.copy()
            signal_data['symbol'] = converted_symbol
            signal_data['original_symbol'] = original_symbol
            
            # 3. 변환된 심볼로 현재 포지션 조회
            current_position = account.get_position_for_symbol(converted_symbol)
            
            # 4. 실제 거래 수량 계산
            actual_quantity_result = self._calculate_actual_quantity(
                account, signal_data, current_position, strategy_config
            )
            
            if not actual_quantity_result['success']:
                return self._error_result(
                    'validation',
                    actual_quantity_result['message'],
                    actual_quantity_result
                )
            
            # 실제 수량으로 시그널 데이터 업데이트
            signal_data['quantity'] = actual_quantity_result['quantity']
            
            # 5. 포지션 전환 타입 결정
            transition_type = self._calculate_transition_type(current_position, signal_data)
            
            # 6. 주문 생성
            trade_order = TradeOrder.from_signal(signal_data, account.account_id, transition_type)
            
            # 7. 리스크 체크
            risk_check = self._check_all_risks(account, trade_order, strategy_config)
            if not risk_check['approved']:
                return self._error_result(
                    'risk',
                    f"Risk check failed: {risk_check['reason']}",
                    risk_check
                )
            
            # 8. 주문 실행
            execution_result = self._execute_trade_order(account, trade_order, strategy_config)
            
            if execution_result['success']:
                return {
                    'success': True,
                    'trade_id': execution_result['trade_id'],
                    'order_id': execution_result['order_id'],
                    'message': f"Order executed successfully: {trade_order.symbol}",
                    'error_type': None,
                    'details': {
                        'symbol': trade_order.symbol,
                        'original_symbol': original_symbol,
                        'action': trade_order.action,
                        'quantity': trade_order.quantity,
                        'transition_type': transition_type.value,
                        'filled': execution_result.get('filled', False),
                        'symbol_converted': converted_symbol != original_symbol
                    }
                }
            else:
                return self._error_result(
                    'broker',
                    f"Order execution failed: {execution_result.get('error', 'Unknown error')}"
                )
            
        except Exception as e:
            logger.error(f"Signal execution failed: {e}")
            return self._error_result(
                'system',
                f"System error during signal execution: {str(e)}"
            )
    
    def _calculate_actual_quantity(self, account: Account, signal_data: Dict,
                               current_position: Dict, strategy_config=None) -> Dict:
        """
        실제 거래 수량 계산
        
        Returns:
            Dict: {
                'success': bool,
                'quantity': int,
                'message': str,
                'is_full_trade': bool
            }
        """
        try:
            # 이미 변환된 심볼 사용
            symbol = signal_data.get('symbol', '')
            original_quantity = signal_data.get('quantity', 0)
            action = signal_data.get('action', '').upper()
            current_qty = current_position.get('quantity', 0)
            
            # 전량 거래인지 확인 (quantity가 0 또는 -1)
            is_full_trade = original_quantity in [0, -1]
            
            if not is_full_trade:
                # 명시적 수량이 지정된 경우
                if original_quantity > 0:
                    return {
                        'success': True,
                        'quantity': original_quantity,
                        'message': f'Using specified quantity: {original_quantity}',
                        'is_full_trade': False
                    }
                else:
                    return {
                        'success': False,
                        'quantity': 0,
                        'message': f'Invalid quantity specified: {original_quantity}',
                        'is_full_trade': False
                    }
            
            # 전량 거래 로직
            if action == 'SELL':
                if current_qty > 0:
                    # 롱 포지션 전량 매도
                    actual_quantity = current_qty
                    logger.info(f"SELL: Closing long position {current_qty} for {symbol}")
                elif current_qty < 0:
                    # 이미 숏 포지션이 있는 경우 - 경고하고 스킵
                    return {
                        'success': False,
                        'quantity': 0,
                        'message': f'Cannot sell: already in short position ({current_qty}) for {symbol}',
                        'is_full_trade': True
                    }
                else:
                    # 포지션이 없는 경우
                    if account.account_type == AccountType.FUTURES:
                        # 선물은 숏 진입 가능 - 기본 수량 사용
                        actual_quantity = self._get_default_quantity(account, symbol, strategy_config)
                        logger.info(f"SELL: Opening short position {actual_quantity} for {symbol}")
                    else:
                        return {
                            'success': False,
                            'quantity': 0,
                            'message': f'Cannot sell: no position to close and not futures account for {symbol}',
                            'is_full_trade': True
                        }
            
            elif action == 'BUY':
                if current_qty < 0:
                    # 숏 포지션 전량 청산
                    actual_quantity = abs(current_qty)
                    logger.info(f"BUY: Closing short position {current_qty} for {symbol}")
                elif current_qty > 0:
                    # 이미 롱 포지션이 있는 경우 - 기본 수량으로 추가 매수
                    actual_quantity = self._get_default_quantity(account, symbol, strategy_config)
                    logger.info(f"BUY: Adding to long position {actual_quantity} for {symbol} (current: {current_qty})")
                else:
                    # 포지션이 없는 경우 - 기본 수량으로 롱 진입
                    actual_quantity = self._get_default_quantity(account, symbol, strategy_config)
                    logger.info(f"BUY: Opening long position {actual_quantity} for {symbol}")
            
            else:
                return {
                    'success': False,
                    'quantity': 0,
                    'message': f'Invalid action: {action}',
                    'is_full_trade': True
                }
            
            if actual_quantity <= 0:
                return {
                    'success': False,
                    'quantity': 0,
                    'message': f'Calculated quantity is zero or negative: {actual_quantity} for {symbol}',
                    'is_full_trade': True
                }
            
            return {
                'success': True,
                'quantity': actual_quantity,
                'message': f'Calculated quantity: {actual_quantity} for {symbol} (action: {action}, current: {current_qty})',
                'is_full_trade': True
            }
            
        except Exception as e:
            logger.error(f"Quantity calculation failed: {e}")
            return {
                'success': False,
                'quantity': 0,
                'message': f'Quantity calculation error: {str(e)}',
                'is_full_trade': False
            }
    
    def _get_default_quantity(self, account: Account, symbol: str, strategy_config=None) -> int:
        """거래 수량 계산 - 레버리지 적용"""
        try:
            if account.account_type == AccountType.FUTURES and strategy_config:
                return self._calculate_futures_quantity_with_leverage(account, symbol, strategy_config)
            else:
                # 주식 로직
                orderable = account.get_orderable_amount(symbol)
                orderable_qty = orderable.get('orderable_quantity', 0)
                return max(1, int(orderable_qty * 0.1)) if orderable_qty > 0 else 1
                
        except Exception as e:
            logger.error(f"Failed to get default quantity for {symbol}: {e}")
            return 1

    def _calculate_futures_quantity_with_leverage(self, account: Account, symbol: str, strategy_config) -> int:
        """레버리지 적용 선물 수량 계산"""
        try:
            # 설정값
            leverage = getattr(strategy_config, 'leverage', 1.0)
            max_position_ratio = getattr(strategy_config, 'max_position_ratio', 1.0)
            
            # 계좌 잔고
            balance = account.get_balance()
            total_balance = balance.get('total_balance', 0)
            
            if total_balance <= 0:
                logger.warning(f"Invalid balance for futures calculation: {total_balance}")
                return 1
            
            # 선물 정보
            current_price = account.broker.get_futures_current_price(symbol)
            multiplier = account.broker.get_futures_multiplier(symbol)
            
            if current_price <= 0:
                logger.warning(f"Invalid price for {symbol}: {current_price}")
                return 1
            
            # 수량 계산
            investable_amount = total_balance * leverage * max_position_ratio
            contract_value = current_price * multiplier
            calculated_quantity = int(investable_amount / contract_value)
            
            final_quantity = max(1, calculated_quantity)
            
            logger.info(f"Futures quantity calculated for {symbol}: {final_quantity} contracts "
                       f"(balance: {total_balance:,.0f}, leverage: {leverage}, "
                       f"price: {current_price}, multiplier: {multiplier})")
            
            return final_quantity
            
        except Exception as e:
            logger.error(f"Leverage calculation failed for {symbol}: {e}")
            return 1

    def place_order(self, account: Account, order_data: Dict) -> Dict:
        """
        단일 주문 실행
        
        Returns:
            Dict: {'success': bool, 'order_id': str, 'error': str}
        """
        try:
            if order_data['action'] == 'BUY':
                order_id = account.broker.buy(
                    symbol=order_data['symbol'],
                    quantity=order_data['quantity'],
                    price=order_data.get('price')
                )
            else:  # SELL
                order_id = account.broker.sell(
                    symbol=order_data['symbol'],
                    quantity=order_data['quantity'],
                    price=order_data.get('price')
                )
            
            logger.info(f"Order placed successfully: {order_id}")
            return {
                'success': True,
                'order_id': order_id,
                'error': None
            }
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return {
                'success': False,
                'order_id': None,
                'error': str(e)
            }
    
    def wait_for_fill(self, account: Account, order_id: str, timeout_seconds: int = 60) -> Tuple[bool, Dict]:
        """주문 체결 대기"""
        start_time = time.time()
        last_status = {}
        
        while time.time() - start_time < timeout_seconds:
            try:
                time.sleep(1)
                status = account.broker.get_order_status(order_id)
                last_status = status
                
                if status['status'] == 'FILLED':
                    logger.info(f"Order filled: {order_id}")
                    return True, status
                elif status['status'] in ['FAILED', 'REJECTED', 'CANCELLED']:
                    logger.error(f"Order failed: {order_id} - {status['status']}")
                    return False, status
                
                time.sleep(4)
                
            except Exception as e:
                logger.error(f"Error checking order status: {e}")
                time.sleep(5)
        
        logger.warning(f"Order wait timeout: {order_id}")
        return False, last_status
    
    # ========== 리스크 체크 ==========
    
    def _check_all_risks(self, account: Account, trade_order: TradeOrder, strategy_config) -> Dict:
        """
        모든 리스크 체크
        
        Returns:
            Dict: {
                'approved': bool,
                'reason': str,
                'checks': dict,
                'details': dict
            }
        """
        checks = {}
        
        try:
            # 1. 계좌 활성화 상태
            checks['account_active'] = account.is_active
            if not account.is_active:
                return {
                    'approved': False,
                    'reason': 'account_inactive',
                    'checks': checks,
                    'details': {'account_id': account.account_id}
                }
            
            # 2. 거래 가능 금액 체크
            estimated_amount = trade_order.get_estimated_value()
            if estimated_amount > 0:
                trade_check = account.can_trade(estimated_amount)
                checks['sufficient_balance'] = trade_check['can_trade']
                
                if not trade_check['can_trade']:
                    return {
                        'approved': False,
                        'reason': trade_check.get('reason', 'insufficient_balance'),
                        'checks': checks,
                        'details': trade_check
                    }
            
            # 3. 포지션 한도 체크
            position_check = self.check_position_limit(account, trade_order.symbol, estimated_amount)
            checks['position_limit'] = position_check['approved']
            if not position_check['approved']:
                return {
                    'approved': False,
                    'reason': 'position_limit_exceeded',
                    'checks': checks,
                    'details': position_check
                }
            
            # 4. 일일 손실 한도 체크
            daily_loss_check = self.check_daily_loss_limit(account.account_id, estimated_amount)
            checks['daily_loss_limit'] = daily_loss_check['approved']
            if not daily_loss_check['approved']:
                return {
                    'approved': False,
                    'reason': 'daily_loss_limit_exceeded',
                    'checks': checks,
                    'details': daily_loss_check
                }
            
            # 모든 체크 통과
            return {
                'approved': True,
                'reason': 'all_risk_checks_passed',
                'checks': checks,
                'details': {
                    'estimated_amount': estimated_amount,
                    'strategy_name': strategy_config.name if hasattr(strategy_config, 'name') else 'unknown'
                }
            }
            
        except Exception as e:
            logger.error(f"Risk check failed: {e}")
            return {
                'approved': False,
                'reason': 'risk_check_system_error',
                'checks': checks,
                'details': {'error': str(e)}
            }
    
    def check_position_limit(self, account: Account, symbol: str, amount: float) -> Dict:
        """포지션 한도 체크"""
        try:
            portfolio_value = account.get_total_portfolio_value()
            
            if portfolio_value <= 0:
                return {'approved': False, 'reason': 'zero_portfolio_value'}
            
            position_ratio = amount / portfolio_value
            max_ratio = 1.0  # 기본 100% 제한
            
            if self.config:
                # 왜 모든 전략에 대해 검사해서 최소값을 찾는거지? 각 전략의 리스크만 검사해야지
                all_strategies = self.config.get_all_strategies()
                for strategy in all_strategies.values():
                    if strategy.account_id == account.account_id and strategy.is_active:
                        max_ratio = min(max_ratio, strategy.max_position_ratio)
            
            approved = position_ratio <= max_ratio
            
            return {
                'approved': approved,
                'reason': 'position_limit_ok' if approved else 'position_limit_exceeded',
                'position_ratio': position_ratio,
                'max_ratio': max_ratio,
                'portfolio_value': portfolio_value,
                'requested_amount': amount
            }
            
        except Exception as e:
            logger.error(f"Position limit check failed: {e}")
            return {
                'approved': False,
                'reason': 'position_limit_check_error',
                'error': str(e)
            }
    
    def check_daily_loss_limit(self, account_id: str, amount: float) -> Dict:
        """일일 손실 한도 체크"""
        try:
            daily_pnl = self.db.get_daily_pnl(account_id, date.today())
            max_loss = -5000000  # 기본 500만원 손실 제한
            
            if self.config:
                # 여기도 왜 모든 전략 대상으로 비교하는거지?
                all_strategies = self.config.get_all_strategies()
                for strategy in all_strategies.values():
                    if strategy.account_id == account_id and strategy.is_active:
                        max_loss = max(max_loss, -strategy.max_daily_loss)  # 음수로 변환
            
            approved = daily_pnl > max_loss
            
            return {
                'approved': approved,
                'reason': 'daily_loss_ok' if approved else 'daily_loss_limit_exceeded',
                'daily_pnl': daily_pnl,
                'max_loss': max_loss,
                'remaining_loss_allowance': daily_pnl - max_loss
            }
            
        except Exception as e:
            logger.error(f"Daily loss limit check failed: {e}")
            # 체크 실패 시 거래 허용
            return {
                'approved': True,
                'reason': 'daily_loss_check_error_allow',
                'error': str(e)
            }
    
    # ========== 주문 실행 로직 ==========
    
    def _execute_trade_order(self, account: Account, trade_order: TradeOrder, strategy_config) -> Dict:
        """거래 주문 실행"""
        strategy_id = 1  # 기본값
        if hasattr(strategy_config, 'name'):
            # 전략 이름으로 DB에서 ID 조회
            try:
                db_strategy = self.db.get_strategy_config(strategy_config.name)
                if db_strategy:
                    strategy_id = db_strategy.get('id', 1)
            except Exception as e:
                logger.warning(f"Could not get strategy ID: {e}")
        
        trade_data = {
            'account_id': account.account_id,
            'strategy_id': strategy_id,
            'symbol': trade_order.symbol,
            'action': trade_order.action,
            'transition_type': trade_order.transition_type.value,
            'quantity': trade_order.quantity,
            'price': trade_order.price,
            'signal_time': datetime.now()
        }
        trade_id = self.db.save_trade(trade_data)
        
        try:
            # 포지션 전환이 필요한 경우
            if trade_order.transition_type == TransitionType.REVERSE:
                return self._execute_reverse_position(account, trade_order, trade_id)
            
            # 일반 주문 실행
            order_result = self.place_order(account, trade_order.to_broker_format())
            
            if not order_result['success']:
                self.db.update_trade_status(trade_id, TradeStatus.FAILED.value, {
                    'error': order_result['error']
                })
                return {
                    'success': False,
                    'trade_id': trade_id,
                    'order_id': None,
                    'error': order_result['error']
                }
            
            order_id = order_result['order_id']
            
            # 체결 대기
            filled, fill_info = self.wait_for_fill(account, order_id)
            
            # 상태 업데이트
            fill_data = {
                'broker_order_id': order_id,
                'filled_quantity': fill_info.get('filled_quantity', trade_order.quantity if filled else 0),
                'avg_fill_price': fill_info.get('avg_fill_price', trade_order.price),
                'fill_time': datetime.now()
            }
            status = TradeStatus.FILLED.value if filled else TradeStatus.FAILED.value
            self.db.update_trade_status(trade_id, status, fill_data)
            
            return {
                'success': filled,
                'trade_id': trade_id,
                'order_id': order_id,
                'filled': filled,
                'fill_info': fill_info,
                'error': None if filled else f"Order not filled: {fill_info.get('error', 'Unknown')}"
            }
            
        except Exception as e:
            logger.error(f"Trade order execution failed: {e}")
            self.db.update_trade_status(trade_id, TradeStatus.FAILED.value, {
                'error': str(e)
            })
            return {
                'success': False,
                'trade_id': trade_id,
                'order_id': None,
                'error': str(e)
            }
    
    def _execute_reverse_position(self, account: Account, trade_order: TradeOrder, trade_id: int) -> Dict:
        """포지션 방향 전환 실행"""
        logger.info(f"Starting position reversal for {trade_order.symbol}")
        
        try:
            # 1단계: 기존 포지션 확인 및 청산
            current_position = account.get_position_for_symbol(trade_order.symbol)
            exit_success = False
            exit_order_id = None
            
            if current_position['quantity'] != 0:
                logger.info(f"Existing position found: {current_position['quantity']} shares")
                
                # 청산 주문 생성 및 실행
                exit_action = 'SELL' if current_position['quantity'] > 0 else 'BUY'
                exit_order = {
                    'symbol': trade_order.symbol,
                    'action': exit_action,
                    'quantity': abs(current_position['quantity']),
                    'price': None  # 시장가로 확실한 청산
                }
                
                exit_result = self.place_order(account, exit_order)
                
                if exit_result['success']:
                    exit_order_id = exit_result['order_id']
                    logger.info(f"Exit order placed: {exit_order_id}")
                    
                    # 청산 체결 대기
                    exit_filled, exit_fill_info = self.wait_for_fill(account, exit_order_id, timeout_seconds=120)
                    exit_success = exit_filled
                    
                    if not exit_filled:
                        logger.error(f"Exit order failed: {exit_order_id}")
                        return self._reverse_position_failed(
                            trade_id, "Exit order failed", exit_order_id, exit_fill_info
                        )
                else:
                    logger.error(f"Failed to place exit order: {exit_result['error']}")
                    return self._reverse_position_failed(
                        trade_id, f"Exit order placement failed: {exit_result['error']}"
                    )
            else:
                logger.info("No existing position to close")
                exit_success = True
            
            # 2단계: 새 포지션 진입
            if exit_success:
                time.sleep(1)  # 시장 안정화 대기
                
                entry_result = self.place_order(account, trade_order.to_broker_format())
                
                if entry_result['success']:
                    entry_order_id = entry_result['order_id']
                    logger.info(f"Entry order placed: {entry_order_id}")
                    
                    # 진입 체결 대기
                    entry_filled, entry_fill_info = self.wait_for_fill(account, entry_order_id)
                    
                    if entry_filled:
                        logger.info("Position reversal completed successfully")
                        fill_data = {
                            'broker_order_id': entry_order_id,
                            'filled_quantity': entry_fill_info.get('filled_quantity', trade_order.quantity),
                            'avg_fill_price': entry_fill_info.get('avg_fill_price', trade_order.price),
                            'fill_time': datetime.now(),
                            'exit_order_id': exit_order_id
                        }
                        self.db.update_trade_status(trade_id, TradeStatus.FILLED.value, fill_data)
                        
                        return {
                            'success': True,
                            'trade_id': trade_id,
                            'order_id': entry_order_id,
                            'exit_order_id': exit_order_id,
                            'filled': True
                        }
                    else:
                        logger.error("Entry order failed after successful exit")
                        return self._reverse_position_failed(
                            trade_id, "Entry failed after exit", entry_order_id, entry_fill_info, exit_order_id
                        )
                else:
                    logger.error(f"Failed to place entry order: {entry_result['error']}")
                    return self._reverse_position_failed(
                        trade_id, f"Entry order placement failed: {entry_result['error']}", None, None, exit_order_id
                    )
            
        except Exception as e:
            logger.error(f"Unexpected error in position reversal: {e}")
            return self._reverse_position_failed(trade_id, f"Unexpected error: {e}")
    
    def _reverse_position_failed(self, trade_id: int, error_msg: str, 
                               entry_order_id: str = None, entry_fill_info: dict = None,
                               exit_order_id: str = None) -> Dict:
        """포지션 전환 실패 처리"""
        fill_data = {
            'broker_order_id': entry_order_id or 'failed',
            'filled_quantity': 0,
            'avg_fill_price': 0,
            'fill_time': datetime.now(),
            'error': error_msg
        }
        
        if exit_order_id:
            fill_data['exit_order_id'] = exit_order_id
        if entry_fill_info:
            fill_data['entry_fill_info'] = entry_fill_info
            
        self.db.update_trade_status(trade_id, TradeStatus.FAILED.value, fill_data)
        
        return {
            'success': False,
            'trade_id': trade_id,
            'order_id': entry_order_id,
            'exit_order_id': exit_order_id,
            'error': error_msg
        }
    
    # ========== 기타 메서드 ==========
    
    def _calculate_transition_type(self, current_position: Dict, signal_data: Dict) -> TransitionType:
        """포지션 전환 타입 계산"""
        current_qty = current_position.get('quantity', 0)
        signal_action = signal_data['action'].upper()
        signal_qty = signal_data.get('quantity', 0)
        
        # 현재 포지션이 없는 경우
        if current_qty == 0:
            return TransitionType.ENTRY
        
        # 현재 롱 포지션
        if current_qty > 0:
            if signal_action == 'SELL':
                if signal_qty >= current_qty:
                    # 전량 또는 초과 매도 - 청산 또는 역전
                    return TransitionType.REVERSE if signal_qty > current_qty else TransitionType.EXIT
                else:
                    # 부분 매도 - 청산
                    return TransitionType.EXIT
            else:  # BUY
                # 추가 매수 - 진입
                return TransitionType.ENTRY
        
        # 현재 숏 포지션
        else:  # current_qty < 0
            if signal_action == 'BUY':
                if signal_qty >= abs(current_qty):
                    # 전량 또는 초과 매수 - 청산 또는 역전
                    return TransitionType.REVERSE if signal_qty > abs(current_qty) else TransitionType.EXIT
                else:
                    # 부분 매수 - 청산
                    return TransitionType.EXIT
            else:  # SELL
                # 추가 매도 - 진입
                return TransitionType.ENTRY
    
    def _error_result(self, error_type: str, message: str, details: dict = None) -> Dict:
        """표준화된 에러 결과 생성"""
        return {
            'success': False,
            'trade_id': None,
            'order_id': None,
            'message': message,
            'error_type': error_type,
            'details': details or {}
        }
    
    def force_close_position(self, account: Account, symbol: str) -> Dict:
        """강제 포지션 청산"""
        try:
            current_position = account.get_position_for_symbol(symbol)
            if current_position['quantity'] == 0:
                logger.info(f"No position to close for {symbol}")
                return {'success': True, 'message': 'No position to close'}
            
            # 시장가로 강제 청산
            action = 'SELL' if current_position['quantity'] > 0 else 'BUY'
            order_data = {
                'symbol': symbol,
                'action': action,
                'quantity': abs(current_position['quantity']),
                'price': None
            }
            
            order_result = self.place_order(account, order_data)
            
            if not order_result['success']:
                return {
                    'success': False,
                    'message': f"Failed to place close order: {order_result['error']}"
                }
            
            order_id = order_result['order_id']
            filled, fill_info = self.wait_for_fill(account, order_id, timeout_seconds=30)
            
            if filled:
                logger.info(f"Position force closed: {symbol}")
                return {
                    'success': True,
                    'message': f"Position closed successfully: {symbol}",
                    'order_id': order_id
                }
            else:
                logger.error(f"Failed to force close position: {symbol}")
                return {
                    'success': False,
                    'message': f"Position close order not filled: {symbol}",
                    'order_id': order_id,
                    'fill_info': fill_info
                }
                
        except Exception as e:
            logger.error(f"Error in force close position: {e}")
            return {
                'success': False,
                'message': f"System error during position close: {str(e)}"
            }