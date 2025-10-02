import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigLoader:
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config_path = Path(config_path)
        self._config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self._override_with_env(config)
            return config
        
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML config: {e}")
    
    def _override_with_env(self, config: Dict) -> None:
        webhook_config = config.setdefault('webhook', {})
        
        if webhook_port := os.getenv('WEBHOOK_PORT'):
            webhook_config['port'] = int(webhook_port)
        
        if webhook_host := os.getenv('WEBHOOK_HOST'):
            webhook_config['host'] = webhook_host
        
        if port := os.getenv('PORT'):
            webhook_config['port'] = int(port)
    
    def get_webhook_config(self) -> Dict[str, Any]:
        webhook_config = self._config.get('webhook', {})
        
        if port := os.getenv('PORT'):
            webhook_config['port'] = int(port)
        
        return webhook_config
    
    def get_account(self, account_id: str) -> Optional[Dict]:
        accounts = self._config.get('accounts', {})
        return accounts.get(account_id)
    
    def get_all_accounts(self) -> Dict[str, Dict]:
        return self._config.get('accounts', {})
    
    def get_strategy_by_token(self, webhook_token: str) -> Optional[Dict]:
        for strategy_name, strategy_data in self._config.get('strategies', {}).items():
            if strategy_data.get('webhook_token') == webhook_token:
                return {
                    'name': strategy_name,
                    **strategy_data
                }
        return None
    
    def get_all_strategies(self) -> Dict[str, Dict]:
        return self._config.get('strategies', {})
    
    def get_token_storage_path(self) -> str:
        kis_config = self._config.get('kis_api', {})
        return kis_config.get('token_storage_path', 'secrets/tokens/')
    
    def reload(self) -> None:
        self._config = self._load_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default