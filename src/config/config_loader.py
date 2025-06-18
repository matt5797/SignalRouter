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
    secret_file: str
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
    leverage: float = 1.0

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
        # 데이터베이스 경로
        if db_path := os.getenv('DB_PATH'):
            config['database']['path'] = db_path
        
        # 웹훅 설정
        if webhook_port := os.getenv('WEBHOOK_PORT'):
            config['webhook']['port'] = int(webhook_port)
        
        if secret_key := os.getenv('SECRET_KEY'):
            config['webhook']['secret_key'] = secret_key
    
    def get_database_config(self) -> Dict[str, Any]:
        """데이터베이스 설정 반환"""
        return self._config.get('database', {})
    
    def get_webhook_config(self) -> Dict[str, Any]:
        """웹훅 서버 설정 반환"""
        return self._config.get('webhook', {})
    
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
            secret_file=account_data['secret_file'],
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
    
    def get_futures_mapping_config(self) -> Dict[str, Any]:
        """선물 매핑 설정 반환"""
        return self._config.get('futures_mapping', {})
    
    def get_futures_symbol_mapping(self) -> Dict[str, str]:
        """선물 심볼 매핑 반환"""
        mapping = self.get_futures_mapping_config()
        return mapping.get('symbol_mapping', {})
    
    def get_futures_multipliers(self) -> Dict[str, int]:
        """선물 승수 매핑 반환"""
        mapping = self.get_futures_mapping_config()
        return mapping.get('multipliers', {})
    
    def get_futures_market_codes(self) -> Dict[str, str]:
        """선물 시장 코드 매핑 반환"""
        mapping = self.get_futures_mapping_config()
        return mapping.get('market_codes', {})
    
    def get_futures_expiry_rules(self) -> Dict[str, Dict]:
        """선물 만료 규칙 반환"""
        mapping = self.get_futures_mapping_config()
        return mapping.get('expiry_rules', {})
    
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