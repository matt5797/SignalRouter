"""
AutoTrader - 메인 거래 로직 및 시그널 라우팅
계좌 관리, 포지션 관리, 거래 실행을 조정하는 핵심 클래스
"""

from typing import Dict, Optional
import logging
from ..database import TradingDB
from ..config import ConfigLoader
from ..trading import Account, AccountType, TradeExecutor, PositionManager
from ..models import TradeSignal

import time

logger = logging.getLogger(__name__)


class AutoTrader:
    """메인 거래 로직 및 시그널 라우팅 클래스"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = ConfigLoader(config_path)
        self.db = TradingDB(self.config.get_database_config().get('path', 'data/trading.db'))
        
        # 핵심 컴포넌트 초기화
        self.position_manager = PositionManager(self.db)
        self.trade_executor = TradeExecutor(self.db, self.config)
        
        # 계좌 로드 및 초기화
        self.accounts = self._load_accounts()
        self._emergency_stop = False
        
        logger.info(f"AutoTrader initialized with {len(self.accounts)} accounts")
    
    def process_signal(self, signal_data: Dict) -> Dict:
        """
        시그널 처리 메인 로직
        
        Returns:
            Dict: {
                'success': bool,
                'message': str,
                'signal_data': dict,
                'execution_result': dict,
                'account_id': str,
                'strategy_name': str
            }
        """
        signal_info = {
            'symbol': signal_data.get('symbol', 'UNKNOWN'),
            'action': signal_data.get('action', 'UNKNOWN'),
            'strategy': signal_data.get('strategy', 'UNKNOWN'),
            'webhook_token': signal_data.get('webhook_token', 'UNKNOWN')
        }
        
        if self._emergency_stop:
            logger.warning(f"Emergency stop active - signal ignored: {signal_info}")
            return {
                'success': False,
                'message': 'Emergency stop is active - all trading halted',
                'signal_data': signal_info,
                'execution_result': {'error_type': 'emergency_stop'},
                'account_id': None,
                'strategy_name': signal_info['strategy']
            }
        
        try:
            # 1. 시그널 객체 생성 및 검증
            signal = TradeSignal.from_webhook_payload(signal_data)
            if not signal.is_valid():
                logger.error(f"Invalid signal received: {signal_info}")
                return {
                    'success': False,
                    'message': f'Invalid signal format: {signal_info}',
                    'signal_data': signal_info,
                    'account_id': None,
                    'strategy_name': signal_info['strategy']
                }
            
            # 2. 계좌 라우팅
            account = self._route_signal_to_account(signal_data)
            if not account:
                logger.error(f"Account routing failed for signal: {signal_info}")
                return {
                    'success': False,
                    'message': 'Account routing failed',
                    'signal_data': signal_info,
                    'account_id': None,
                    'strategy_name': signal_info['strategy']
                }
            
            # 3. 거래 실행
            logger.info(f"Executing signal: {signal_info} on account: {account.account_id}")
            execution_result = self.trade_executor.execute_signal(account, signal_data)
            
            if execution_result['success']:
                logger.info(f"Signal executed successfully: {signal_info} -> Order: {execution_result['order_id']}")
                return {
                    'success': True,
                    'message': f"Signal executed successfully: {signal_info['symbol']} {signal_info['action']}",
                    'signal_data': signal_info,
                    'execution_result': execution_result,
                    'account_id': account.account_id,
                    'strategy_name': signal_info['strategy']
                }
            else:
                logger.error(f"Signal execution failed: {execution_result['message']}")
                return {
                    'success': False,
                    'message': execution_result['message'],
                    'signal_data': signal_info,
                    'execution_result': execution_result,
                    'account_id': account.account_id,
                    'strategy_name': signal_info['strategy']
                }
            
        except Exception as e:
            logger.error(f"Unexpected error processing signal {signal_info}: {e}")
            return {
                'success': False,
                'message': f'System error during signal processing: {str(e)}',
                'signal_data': signal_info,
                'account_id': None,
                'strategy_name': signal_info['strategy']
            }
    
    def get_account(self, account_id: str) -> Optional[Account]:
        """계좌 조회"""
        return self.accounts.get(account_id)
    
    def get_all_positions(self) -> Dict:
        """모든 계좌의 포지션 조회"""
        all_positions = {}
        
        for account_id, account in self.accounts.items():
            if account.is_active:
                try:
                    positions = account.get_positions()
                    all_positions[account_id] = positions
                except Exception as e:
                    logger.error(f"Failed to get positions for account {account_id}: {e}")
                    all_positions[account_id] = []
        
        return all_positions
    
    def get_portfolio_summary(self) -> Dict:
        """전체 포트폴리오 요약"""
        summary = {
            'total_accounts': len(self.accounts),
            'active_accounts': 0,
            'total_portfolio_value': 0.0,
            'total_unrealized_pnl': 0.0,
            'accounts_detail': {}
        }
        
        for account_id, account in self.accounts.items():
            if account.is_active:
                summary['active_accounts'] += 1
                
                try:
                    portfolio_value = account.get_total_portfolio_value()
                    unrealized_pnl = account.get_total_unrealized_pnl()
                    positions = account.get_positions()
                    
                    summary['total_portfolio_value'] += portfolio_value
                    summary['total_unrealized_pnl'] += unrealized_pnl
                    
                    summary['accounts_detail'][account_id] = {
                        'name': account.name,
                        'type': account.account_type.value,
                        'portfolio_value': portfolio_value,
                        'unrealized_pnl': unrealized_pnl,
                        'positions_count': len(positions)
                    }
                    
                except Exception as e:
                    logger.error(f"Failed to get portfolio data for account {account_id}: {e}")
                    summary['accounts_detail'][account_id] = {
                        'name': account.name,
                        'type': account.account_type.value,
                        'portfolio_value': 0.0,
                        'unrealized_pnl': 0.0,
                        'positions_count': 0,
                        'error': str(e)
                    }
        
        return summary
    
    def emergency_stop_all(self) -> Dict:
        """비상 정지 - 모든 거래 중단"""
        self._emergency_stop = True
        logger.critical("EMERGENCY STOP ACTIVATED - All trading halted")
        
        stopped_accounts = []
        for account_id, account in self.accounts.items():
            if account.is_active:
                account.is_active = False
                stopped_accounts.append(account_id)
        
        return {
            'success': True,
            'message': 'Emergency stop activated successfully',
            'stopped_accounts': stopped_accounts,
            'total_stopped': len(stopped_accounts)
        }
    
    def resume_trading(self) -> Dict:
        """거래 재개"""
        self._emergency_stop = False
        logger.info("Trading resumed - reactivating accounts")
        
        resumed_accounts = []
        failed_accounts = []
        
        # 설정에 따라 계좌 재활성화
        for account_id, account in self.accounts.items():
            try:
                config = self.config.get_account_config(account_id)
                if config and config.is_active:
                    account.is_active = True
                    resumed_accounts.append(account_id)
            except Exception as e:
                logger.error(f"Failed to resume account {account_id}: {e}")
                failed_accounts.append({'account_id': account_id, 'error': str(e)})
        
        return {
            'success': len(failed_accounts) == 0,
            'message': f'Trading resumed for {len(resumed_accounts)} accounts',
            'resumed_accounts': resumed_accounts,
            'failed_accounts': failed_accounts
        }
    
    def _route_signal_to_account(self, signal_data: Dict) -> Optional[Account]:
        """
        시그널을 적절한 계좌로 라우팅
        """
        webhook_token = signal_data.get('webhook_token')
        if not webhook_token:
            logger.error("No webhook token in signal")
            return None
        
        # 토큰으로 전략 찾기
        strategy_config = self.config.get_strategy_by_token(webhook_token)
        if not strategy_config:
            logger.error(f"Strategy not found for token: {webhook_token}")
            return None
        
        # 전략이 비활성화된 경우
        if not strategy_config.is_active:
            logger.error(f"Strategy {strategy_config.name} is inactive")
            return None
        
        # 계좌 확인
        account = self.accounts.get(strategy_config.account_id)
        if not account:
            logger.error(f"Account {strategy_config.account_id} not found")
            return None
        
        if not account.is_active:
            logger.error(f"Account {strategy_config.account_id} is inactive")
            return None
        
        return account
    
    def _load_accounts(self) -> Dict[str, Account]:
        """설정에서 계좌 로드"""
        accounts = {}
        account_configs = self.config.get_all_accounts()
        
        kis_config = self.config.get('kis_api', {})
        token_storage_path = kis_config.get('token_storage_path', 'secrets/tokens/')
        
        load_errors = []
        
        for account_id, config in account_configs.items():
            try:
                account = Account(
                    account_id=config.account_id,
                    name=config.name,
                    account_type=AccountType(config.type),
                    secret_file_path=config.secret_file,
                    is_virtual=config.is_virtual,
                    is_active=config.is_active,
                    token_storage_path=token_storage_path
                )
                accounts[account_id] = account
                logger.info(f"Account loaded: {account_id} (type: {config.type}, virtual: {config.is_virtual})")
                
            except Exception as e:
                logger.error(f"Failed to load account {account_id}: {e}")
        
        if not accounts:
            logger.error("No accounts loaded successfully")
        else:
            active_count = sum(1 for acc in accounts.values() if acc.is_active)
            logger.info(f"Total accounts loaded: {len(accounts)}, Active: {active_count}")
        
        return accounts
    
    def get_system_status(self) -> Dict:
        """시스템 상태"""
        try:
            portfolio_summary = self.get_portfolio_summary()
            
            return {
                'emergency_stop': self._emergency_stop,
                'total_accounts': len(self.accounts),
                'active_accounts': portfolio_summary['active_accounts'],
                'total_portfolio_value': portfolio_summary['total_portfolio_value'],
                'total_unrealized_pnl': portfolio_summary['total_unrealized_pnl'],
                'status': 'emergency_stop' if self._emergency_stop else 'operational',
                'timestamp': logger.handlers[0].formatter.formatTime(logger.makeRecord(
                    '', 0, '', 0, '', (), None)) if logger.handlers else 'unknown'
            }
            
        except Exception as e:
            logger.error(f"System status check failed: {e}")
            return {
                'emergency_stop': self._emergency_stop,
                'status': 'error',
                'error': str(e),
                'timestamp': 'unknown'
            }