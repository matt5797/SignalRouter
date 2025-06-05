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
    
    def process_signal(self, signal_data: Dict) -> bool:
        """시그널 처리 메인 로직"""
        if self._emergency_stop:
            logger.warning("Emergency stop active - signal ignored")
            return False
        
        try:
            # 시그널 객체 생성 및 검증
            signal = TradeSignal.from_webhook_payload(signal_data)
            if not signal.is_valid():
                logger.error(f"Invalid signal: {signal_data}")
                return False
            
            # 계좌 라우팅
            account = self._route_signal_to_account(signal_data)
            if not account:
                logger.error(f"No account found for signal: {signal.strategy}")
                return False
            
            # 거래 실행
            return self.trade_executor.execute_signal(account, signal_data)
            
        except Exception as e:
            logger.error(f"Failed to process signal: {e}")
            return False
    
    def get_account(self, account_id: str) -> Optional[Account]:
        """계좌 조회"""
        return self.accounts.get(account_id)
    
    def get_all_positions(self) -> Dict:
        """모든 계좌의 포지션 조회"""
        all_positions = {}
        for account_id, account in self.accounts.items():
            if account.is_active:
                all_positions[account_id] = account.get_positions()
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
                portfolio_value = account.get_total_portfolio_value()
                unrealized_pnl = account.get_total_unrealized_pnl()
                
                summary['total_portfolio_value'] += portfolio_value
                summary['total_unrealized_pnl'] += unrealized_pnl
                
                summary['accounts_detail'][account_id] = {
                    'name': account.name,
                    'type': account.account_type.value,
                    'portfolio_value': portfolio_value,
                    'unrealized_pnl': unrealized_pnl,
                    'positions_count': len(account.get_positions())
                }
        
        return summary
    
    def emergency_stop_all(self) -> None:
        """비상 정지 - 모든 거래 중단"""
        self._emergency_stop = True
        logger.critical("EMERGENCY STOP ACTIVATED - All trading halted")
        
        # 모든 계좌 비활성화
        for account in self.accounts.values():
            account.is_active = False
    
    def resume_trading(self) -> None:
        """거래 재개"""
        self._emergency_stop = False
        logger.info("Trading resumed - reactivating accounts")
        
        # 설정에 따라 계좌 재활성화
        for account_id, account in self.accounts.items():
            config = self.config.get_account_config(account_id)
            if config and config.is_active:
                account.is_active = True
    
    def _load_accounts(self) -> Dict[str, Account]:
        """설정에서 계좌 로드"""
        accounts = {}
        account_configs = self.config.get_all_accounts()
        
        # 실전투자 계좌들 찾기
        real_accounts = {
            account_id: config for account_id, config in account_configs.items() 
            if not config.is_virtual
        }
        
        # 모의투자용 기본 실전투자 계좌 결정
        default_real_account_id = self.config.get('pykis.default_real_account_id')
        default_real_secret = None
        
        if real_accounts:
            if default_real_account_id and default_real_account_id in real_accounts:
                # 지정된 실전투자 계좌 사용
                default_real_secret = real_accounts[default_real_account_id].secret_file
                logger.info(f"Using {default_real_account_id} as default real account for virtual trading")
            else:
                # 첫 번째 실전투자 계좌 사용
                first_real_account = next(iter(real_accounts.values()))
                default_real_secret = first_real_account.secret_file
                logger.info(f"Using {first_real_account.account_id} as default real account for virtual trading")
        else:
            logger.warning("No real accounts found - virtual accounts may not work properly")
        
        # 계좌 생성
        for account_id, config in account_configs.items():
            try:
                account = Account(
                    account_id=config.account_id,
                    name=config.name,
                    account_type=AccountType(config.type),
                    secret_file_path=config.secret_file,
                    is_virtual=config.is_virtual,
                    is_active=config.is_active,
                    default_real_secret=default_real_secret if config.is_virtual else None
                )
                accounts[account_id] = account
                logger.info(f"Account loaded: {account_id} (virtual: {config.is_virtual})")
                
            except Exception as e:
                logger.error(f"Failed to load account {account_id}: {e}")
        
        return accounts
    
    def _route_signal_to_account(self, signal_data: Dict) -> Optional[Account]:
        """시그널을 적절한 계좌로 라우팅"""
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
            logger.warning(f"Strategy {strategy_config.name} is inactive")
            return None
        
        # 계좌 반환
        account = self.accounts.get(strategy_config.account_id)
        if not account or not account.is_active:
            logger.error(f"Account {strategy_config.account_id} not found or inactive")
            return None
        
        return account
    
    def _load_config(self) -> Dict:
        """설정 로드 (내부 메서드)"""
        return {
            'database': self.config.get_database_config(),
            'risk_management': self.config.get_risk_management_config(),
            'webhook': self.config.get_webhook_config()
        }