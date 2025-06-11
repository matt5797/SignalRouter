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

logger = logging.getLogger(__name__)


class AutoTrader:
    """메인 거래 로직 및 시그널 라우팅 클래스"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = ConfigLoader(config_path)
        self.db = TradingDB(self.config.get_database_config().get('path', 'data/trading.db'))
        
        # 핵심 컴포넌트 초기화
        self.position_manager = PositionManager(self.db)
        self.trade_executor = TradeExecutor(self.db)
        
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
                    'execution_result': {'error_type': 'validation', 'details': 'Invalid signal format'},
                    'account_id': None,
                    'strategy_name': signal_info['strategy']
                }
            
            # 2. 계좌 라우팅
            account_routing = self._route_signal_to_account(signal_data)
            if not account_routing['success']:
                logger.error(f"Account routing failed: {account_routing['message']} for signal: {signal_info}")
                return {
                    'success': False,
                    'message': account_routing['message'],
                    'signal_data': signal_info,
                    'execution_result': {
                        'error_type': 'routing',
                        'details': account_routing['details']
                    },
                    'account_id': account_routing.get('account_id'),
                    'strategy_name': signal_info['strategy']
                }
            
            account = account_routing['account']
            account_id = account.account_id
            
            # 3. 거래 실행
            logger.info(f"Executing signal: {signal_info} on account: {account_id}")
            execution_result = self.trade_executor.execute_signal(account, signal_data)
            
            if execution_result['success']:
                logger.info(f"Signal executed successfully: {signal_info} -> Order: {execution_result['order_id']}")
                return {
                    'success': True,
                    'message': f"Signal executed successfully: {signal_info['symbol']} {signal_info['action']}",
                    'signal_data': signal_info,
                    'execution_result': execution_result,
                    'account_id': account_id,
                    'strategy_name': signal_info['strategy']
                }
            else:
                # 실행 실패 로깅 - 에러 타입별 로그 레벨 구분
                error_type = execution_result.get('error_type', 'unknown')
                if error_type in ['validation', 'risk']:
                    logger.warning(f"Signal execution rejected ({error_type}): {execution_result['message']}")
                else:
                    logger.error(f"Signal execution failed ({error_type}): {execution_result['message']}")
                
                return {
                    'success': False,
                    'message': execution_result['message'],
                    'signal_data': signal_info,
                    'execution_result': execution_result,
                    'account_id': account_id,
                    'strategy_name': signal_info['strategy']
                }
            
        except Exception as e:
            logger.error(f"Unexpected error processing signal {signal_info}: {e}")
            return {
                'success': False,
                'message': f'System error during signal processing: {str(e)}',
                'signal_data': signal_info,
                'execution_result': {
                    'error_type': 'system',
                    'details': {'exception': str(e), 'exception_type': type(e).__name__}
                },
                'account_id': None,
                'strategy_name': signal_info['strategy']
            }
    
    def get_account(self, account_id: str) -> Optional[Account]:
        """계좌 조회"""
        return self.accounts.get(account_id)
    
    def get_all_positions(self) -> Dict:
        """모든 계좌의 포지션 조회"""
        all_positions = {}
        errors = {}
        
        for account_id, account in self.accounts.items():
            if account.is_active:
                try:
                    positions_meta = account.get_positions_with_meta()
                    all_positions[account_id] = {
                        'positions': positions_meta['data'],
                        'status': positions_meta['status'],
                        'reliable': positions_meta.get('status') in ['success', 'cached'],
                        'error': positions_meta.get('error')
                    }
                except Exception as e:
                    logger.error(f"Failed to get positions for account {account_id}: {e}")
                    errors[account_id] = str(e)
                    all_positions[account_id] = {
                        'positions': [],
                        'status': 'error',
                        'reliable': False,
                        'error': str(e)
                    }
        
        result = {
            'positions_by_account': all_positions,
            'total_accounts': len(self.accounts),
            'active_accounts': len([acc for acc in self.accounts.values() if acc.is_active]),
            'accounts_with_errors': len(errors)
        }
        
        if errors:
            result['errors'] = errors
            logger.warning(f"Position retrieval errors for {len(errors)} accounts")
        
        return result
    
    def get_portfolio_summary(self) -> Dict:
        """전체 포트폴리오 요약"""
        summary = {
            'total_accounts': len(self.accounts),
            'active_accounts': 0,
            'reliable_accounts': 0,
            'total_portfolio_value': 0.0,
            'total_unrealized_pnl': 0.0,
            'accounts_detail': {},
            'data_health': {
                'all_reliable': True,
                'unreliable_accounts': [],
                'stale_data_accounts': []
            }
        }
        
        for account_id, account in self.accounts.items():
            if account.is_active:
                summary['active_accounts'] += 1
                
                try:
                    # 포트폴리오 가치
                    portfolio_result = account.get_total_portfolio_value()
                    unrealized_result = account.get_total_unrealized_pnl()
                    data_health = account.get_data_health()
                    
                    is_reliable = (portfolio_result['reliable'] and unrealized_result['reliable'])
                    is_stale = account.is_data_stale(max_age_seconds=300)  # 5분
                    
                    if is_reliable:
                        summary['reliable_accounts'] += 1
                        summary['total_portfolio_value'] += portfolio_result['total_value']
                        summary['total_unrealized_pnl'] += unrealized_result['unrealized_pnl']
                    else:
                        summary['data_health']['all_reliable'] = False
                        summary['data_health']['unreliable_accounts'].append(account_id)
                    
                    if is_stale:
                        summary['data_health']['stale_data_accounts'].append(account_id)
                    
                    summary['accounts_detail'][account_id] = {
                        'name': account.name,
                        'type': account.account_type.value,
                        'portfolio_value': portfolio_result['total_value'] if is_reliable else 0.0,
                        'unrealized_pnl': unrealized_result['unrealized_pnl'] if is_reliable else 0.0,
                        'positions_count': len(account.get_positions()),
                        'data_reliable': is_reliable,
                        'data_stale': is_stale,
                        'balance_status': data_health.get('balance_status'),
                        'positions_status': data_health.get('positions_status')
                    }
                    
                except Exception as e:
                    logger.error(f"Failed to get portfolio data for account {account_id}: {e}")
                    summary['data_health']['all_reliable'] = False
                    summary['data_health']['unreliable_accounts'].append(account_id)
                    summary['accounts_detail'][account_id] = {
                        'name': account.name,
                        'type': account.account_type.value,
                        'portfolio_value': 0.0,
                        'unrealized_pnl': 0.0,
                        'positions_count': 0,
                        'data_reliable': False,
                        'error': str(e)
                    }
        
        # 신뢰성 통계
        if summary['active_accounts'] > 0:
            summary['data_health']['reliability_ratio'] = summary['reliable_accounts'] / summary['active_accounts']
        else:
            summary['data_health']['reliability_ratio'] = 0.0
        
        # 경고 로깅
        if not summary['data_health']['all_reliable']:
            logger.warning(f"Portfolio data reliability issues: "
                         f"{len(summary['data_health']['unreliable_accounts'])} unreliable accounts")
        
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
            'total_stopped': len(stopped_accounts),
            'timestamp': logger.handlers[0].formatter.formatTime(logger.makeRecord(
                '', 0, '', 0, '', (), None)) if logger.handlers else 'unknown'
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
                    
                    # 데이터 신선도 체크
                    if account.is_data_stale(max_age_seconds=60):
                        logger.info(f"Refreshing stale data for account {account_id}")
                        account.refresh_data()
                        
            except Exception as e:
                logger.error(f"Failed to resume account {account_id}: {e}")
                failed_accounts.append({'account_id': account_id, 'error': str(e)})
        
        return {
            'success': len(failed_accounts) == 0,
            'message': f'Trading resumed for {len(resumed_accounts)} accounts',
            'resumed_accounts': resumed_accounts,
            'failed_accounts': failed_accounts,
            'total_resumed': len(resumed_accounts),
            'total_failed': len(failed_accounts)
        }
    
    def _route_signal_to_account(self, signal_data: Dict) -> Dict:
        """
        시그널을 적절한 계좌로 라우팅
        
        Returns:
            Dict: {
                'success': bool,
                'account': Account,
                'account_id': str,
                'message': str,
                'details': dict
            }
        """
        webhook_token = signal_data.get('webhook_token')
        if not webhook_token:
            return {
                'success': False,
                'account': None,
                'account_id': None,
                'message': 'No webhook token in signal',
                'details': {'missing_field': 'webhook_token'}
            }
        
        # 토큰으로 전략 찾기
        strategy_config = self.config.get_strategy_by_token(webhook_token)
        if not strategy_config:
            return {
                'success': False,
                'account': None,
                'account_id': None,
                'message': f'Strategy not found for token: {webhook_token}',
                'details': {'webhook_token': webhook_token}
            }
        
        # 전략이 비활성화된 경우
        if not strategy_config.is_active:
            return {
                'success': False,
                'account': None,
                'account_id': strategy_config.account_id,
                'message': f'Strategy {strategy_config.name} is inactive',
                'details': {
                    'strategy_name': strategy_config.name,
                    'strategy_active': False
                }
            }
        
        # 계좌 확인
        account = self.accounts.get(strategy_config.account_id)
        if not account:
            return {
                'success': False,
                'account': None,
                'account_id': strategy_config.account_id,
                'message': f'Account {strategy_config.account_id} not found',
                'details': {
                    'strategy_name': strategy_config.name,
                    'account_id': strategy_config.account_id
                }
            }
        
        if not account.is_active:
            return {
                'success': False,
                'account': account,
                'account_id': account.account_id,
                'message': f'Account {strategy_config.account_id} is inactive',
                'details': {
                    'strategy_name': strategy_config.name,
                    'account_active': False
                }
            }
        
        return {
            'success': True,
            'account': account,
            'account_id': account.account_id,
            'message': f'Routed to account {account.account_id}',
            'details': {
                'strategy_name': strategy_config.name,
                'account_name': account.name,
                'account_type': account.account_type.value
            }
        }
    
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
                error_info = {
                    'account_id': account_id,
                    'error': str(e),
                    'config': {
                        'name': config.name,
                        'type': config.type,
                        'secret_file': config.secret_file
                    }
                }
                load_errors.append(error_info)
                logger.error(f"Failed to load account {account_id}: {e}")
        
        if not accounts:
            logger.error("No accounts loaded successfully")
            if load_errors:
                logger.error(f"Account loading errors: {load_errors}")
        else:
            active_count = sum(1 for acc in accounts.values() if acc.is_active)
            logger.info(f"Total accounts loaded: {len(accounts)}, Active: {active_count}")
            
            if load_errors:
                logger.warning(f"Failed to load {len(load_errors)} accounts")
        
        return accounts
    
    def get_system_health(self) -> Dict:
        """시스템 전체 건강 상태 체크"""
        try:
            portfolio_summary = self.get_portfolio_summary()
            positions_summary = self.get_all_positions()
            
            # 건강 상태 점수 계산 (0-100)
            health_score = 100
            issues = []
            
            # 비상 정지 상태 체크
            if self._emergency_stop:
                health_score -= 50
                issues.append("Emergency stop is active")
            
            # 계좌 신뢰성 체크
            reliability_ratio = portfolio_summary['data_health']['reliability_ratio']
            if reliability_ratio < 1.0:
                health_score -= (1.0 - reliability_ratio) * 30
                issues.append(f"Data reliability issues: {reliability_ratio:.1%} reliable")
            
            # 오래된 데이터 체크
            stale_accounts = len(portfolio_summary['data_health']['stale_data_accounts'])
            if stale_accounts > 0:
                health_score -= min(stale_accounts * 10, 20)
                issues.append(f"{stale_accounts} accounts with stale data")
            
            # 에러가 있는 계좌 체크
            error_accounts = positions_summary.get('accounts_with_errors', 0)
            if error_accounts > 0:
                health_score -= min(error_accounts * 15, 30)
                issues.append(f"{error_accounts} accounts with position errors")
            
            health_score = max(0, health_score)
            
            return {
                'health_score': health_score,
                'status': 'healthy' if health_score >= 80 else 'warning' if health_score >= 50 else 'critical',
                'emergency_stop': self._emergency_stop,
                'total_accounts': len(self.accounts),
                'active_accounts': portfolio_summary['active_accounts'],
                'reliable_accounts': portfolio_summary['reliable_accounts'],
                'data_reliability_ratio': reliability_ratio,
                'issues': issues,
                'portfolio_summary': portfolio_summary,
                'timestamp': logger.handlers[0].formatter.formatTime(logger.makeRecord(
                    '', 0, '', 0, '', (), None)) if logger.handlers else 'unknown'
            }
            
        except Exception as e:
            logger.error(f"System health check failed: {e}")
            return {
                'health_score': 0,
                'status': 'critical',
                'emergency_stop': self._emergency_stop,
                'error': str(e),
                'timestamp': 'unknown'
            }