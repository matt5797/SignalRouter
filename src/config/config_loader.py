"""
ConfigLoader - YAML 설정 파일 관리
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class AccountConfig:
    """계좌 설정 데이터 클래스"""
    account_id: str
    name: str
    type: str
    is_virtual: bool
    is_active: bool


@dataclass
class StrategyConfig:
    """전략 설정 데이터 클래스"""
    name: str
    account_id: str
    webhook_token: str
    max_position_ratio: float
    max_daily_loss: float
    is_active: bool


class ConfigLoader:
    """YAML 설정 파일 로더"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # 환경 변수로 덮어쓰기
            self._override_with_env(config)
            return config
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML config: {e}")
    
    def _override_with_env(self, config: Dict) -> None:
        """환경 변수로 설정 덮어쓰기"""
        # 데이터베이스 설정
        database_config = config.setdefault('database', {})
        
        # Railway 환경변수 지원
        if db_url := os.getenv('DATABASE_URL'):
            database_config['postgresql_url'] = db_url
        elif db_url := os.getenv('POSTGRESQL_URL'):
            database_config['postgresql_url'] = db_url
        elif db_url := os.getenv('POSTGRES_URL'):
            database_config['postgresql_url'] = db_url
        
        # SQLite 경로 (로컬 개발용)
        if db_path := os.getenv('DB_PATH'):
            database_config['path'] = db_path
        
        # 웹훅 설정
        webhook_config = config.setdefault('webhook', {})
        if webhook_port := os.getenv('WEBHOOK_PORT'):
            webhook_config['port'] = int(webhook_port)
        if webhook_host := os.getenv('WEBHOOK_HOST'):
            webhook_config['host'] = webhook_host
        if secret_key := os.getenv('SECRET_KEY'):
            webhook_config['secret_key'] = secret_key
        
        # Railway는 PORT 환경변수를 제공
        if port := os.getenv('PORT'):
            webhook_config['port'] = int(port)
    
    def get_database_config(self) -> Dict[str, Any]:
        """데이터베이스 설정 반환"""
        db_config = self._config.get('database', {})
        
        # 환경변수 재확인 (실행시 변경될 수 있음)
        if db_url := os.getenv('DATABASE_URL'):
            db_config['postgresql_url'] = db_url
        
        return db_config
    
    def is_postgresql_enabled(self) -> bool:
        """PostgreSQL 사용 여부 확인"""
        db_config = self.get_database_config()
        return bool(
            db_config.get('postgresql_url') or
            os.getenv('DATABASE_URL') or
            os.getenv('POSTGRESQL_URL') or
            os.getenv('POSTGRES_URL')
        )
    
    def get_webhook_config(self) -> Dict[str, Any]:
        """웹훅 서버 설정 반환"""
        webhook_config = self._config.get('webhook', {})
        
        # Railway PORT 환경변수 재확인
        if port := os.getenv('PORT'):
            webhook_config['port'] = int(port)
        
        return webhook_config
    
    def get_account_config(self, account_id: str) -> Optional[AccountConfig]:
        """계좌 설정 반환"""
        accounts = self._config.get('accounts', {})
        if account_id not in accounts:
            return None
        
        account_data = accounts[account_id]
        return AccountConfig(
            account_id=account_id,
            name=account_data['name'],
            type=account_data['type'],
            is_virtual=account_data['is_virtual'],
            is_active=account_data['is_active']
        )
    
    def get_all_accounts(self) -> Dict[str, AccountConfig]:
        """모든 계좌 설정 반환"""
        accounts = {}
        for account_id in self._config.get('accounts', {}):
            account_config = self.get_account_config(account_id)
            if account_config:
                accounts[account_id] = account_config
        return accounts
    
    def get_strategy_config(self, strategy_name: str) -> Optional[StrategyConfig]:
        """전략 설정 반환"""
        strategies = self._config.get('strategies', {})
        if strategy_name not in strategies:
            return None
        
        strategy_data = strategies[strategy_name]
        return StrategyConfig(
            name=strategy_name,
            account_id=strategy_data['account_id'],
            webhook_token=strategy_data['webhook_token'],
            max_position_ratio=strategy_data['max_position_ratio'],
            max_daily_loss=strategy_data['max_daily_loss'],
            is_active=strategy_data['is_active']
        )
    
    def get_all_strategies(self) -> Dict[str, StrategyConfig]:
        """모든 전략 설정 반환"""
        strategies = {}
        for strategy_name in self._config.get('strategies', {}):
            strategy_config = self.get_strategy_config(strategy_name)
            if strategy_config:
                strategies[strategy_name] = strategy_config
        return strategies
    
    def get_risk_management_config(self) -> Dict[str, Any]:
        """리스크 관리 설정 반환"""
        return self._config.get('risk_management', {})
    
    def get_logging_config(self) -> Dict[str, Any]:
        """로깅 설정 반환"""
        return self._config.get('logging', {})
    
    def get_dashboard_config(self) -> Dict[str, Any]:
        """대시보드 설정 반환"""
        return self._config.get('dashboard', {})
    
    def get_strategy_by_token(self, webhook_token: str) -> Optional[StrategyConfig]:
        """웹훅 토큰으로 전략 검색"""
        for strategy_name, strategy_data in self._config.get('strategies', {}).items():
            if strategy_data.get('webhook_token') == webhook_token:
                return self.get_strategy_config(strategy_name)
        return None
    
    def reload(self) -> None:
        """설정 파일 다시 로드"""
        self._config = self._load_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        """설정 값 조회 (점 표기법 지원)"""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_deployment_info(self) -> Dict[str, Any]:
        """배포 환경 정보 반환"""
        return {
            'database_type': 'postgresql' if self.is_postgresql_enabled() else 'sqlite',
            'database_url_set': bool(os.getenv('DATABASE_URL')),
            'accounts_config_set': bool(os.getenv('ACCOUNTS_CONFIG')),
            'port': os.getenv('PORT'),
            'railway_environment': bool(os.getenv('RAILWAY_ENVIRONMENT')),
            'heroku_app_name': os.getenv('HEROKU_APP_NAME'),
            'webhook_config': self.get_webhook_config(),
            'database_config': {
                'postgresql_enabled': self.is_postgresql_enabled(),
                'sqlite_path': self.get_database_config().get('path', 'data/trading.db')
            }
        }