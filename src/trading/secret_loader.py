"""
SecretLoader - 환경변수 우선 계좌 정보 로더
JSON 압축 환경변수 방식을 우선 지원하고, 파일 방식을 fallback으로 사용
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class SecretLoader:
    """계좌 비밀 정보 로더 (환경변수 우선)"""
    
    _accounts_cache = None  # 환경변수 파싱 결과 캐시
    
    @staticmethod
    def load_secret(secret_identifier: str) -> Dict:
        """
        계좌 정보 로드 (환경변수 → 파일 순서)
        
        Args:
            secret_identifier: 계좌 ID 또는 파일 경로
            
        Returns:
            계좌 정보 딕셔너리
        """
        try:
            # 1차: 환경변수에서 JSON 배열 로드 시도
            account_data = SecretLoader._load_from_env(secret_identifier)
            if account_data:
                logger.debug(f"Secret loaded from environment: {secret_identifier}")
                return account_data
            
            # 2차: 파일에서 로드 (개발환경 또는 fallback)
            if secret_identifier.endswith('.json') or '/' in secret_identifier:
                account_data = SecretLoader._load_from_file(secret_identifier)
                if account_data:
                    logger.debug(f"Secret loaded from file: {secret_identifier}")
                    return account_data
            
            raise FileNotFoundError(f"Secret not found: {secret_identifier}")
            
        except Exception as e:
            logger.error(f"Failed to load secret {secret_identifier}: {e}")
            raise
    
    @staticmethod
    def _load_from_env(account_id: str) -> Optional[Dict]:
        """환경변수에서 계좌 정보 로드"""
        try:
            # 캐시된 결과가 있으면 재사용
            if SecretLoader._accounts_cache is None:
                accounts_json = os.getenv('ACCOUNTS_CONFIG')
                if not accounts_json:
                    return None
                
                # JSON 파싱
                accounts_list = json.loads(accounts_json)
                if not isinstance(accounts_list, list):
                    logger.error("ACCOUNTS_CONFIG must be a JSON array")
                    return None
                
                # ID를 키로 하는 딕셔너리로 변환
                SecretLoader._accounts_cache = {
                    account.get('id', ''): account 
                    for account in accounts_list 
                    if isinstance(account, dict) and account.get('id')
                }
                
                logger.info(f"Loaded {len(SecretLoader._accounts_cache)} accounts from environment")
            
            # 계좌 ID로 검색
            account_data = SecretLoader._accounts_cache.get(account_id)
            if account_data:
                # 필수 필드 검증
                if SecretLoader.validate_secret(account_data):
                    return account_data
                else:
                    logger.error(f"Invalid account data for {account_id}")
            
            return None
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid ACCOUNTS_CONFIG JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading from environment: {e}")
            return None
    
    @staticmethod
    def _load_from_file(file_path: str) -> Dict:
        """파일에서 계좌 정보 로드 (기존 로직)"""
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"Secret file not found: {file_path}")
            
            with open(path, 'r', encoding='utf-8') as f:
                secret_data = json.load(f)
            
            # 필수 필드 검증
            required_fields = ['app_key', 'app_secret', 'account_number', 'account_product']
            missing_fields = [field for field in required_fields if field not in secret_data]
            
            if missing_fields:
                raise ValueError(f"Missing required fields in secret file: {missing_fields}")
            
            return secret_data
            
        except Exception as e:
            logger.error(f"Failed to load secret from file {file_path}: {e}")
            raise
    
    @staticmethod
    def validate_secret(secret_data: Dict) -> bool:
        """계좌 데이터 유효성 검증"""
        try:
            # 필수 필드 존재 확인
            required_fields = ['app_key', 'app_secret', 'account_number', 'account_product']
            if not all(field in secret_data for field in required_fields):
                return False
            
            # 빈 값 확인
            if not all(str(secret_data[field]).strip() for field in required_fields):
                return False
            
            # 계좌번호 길이 확인 (8자리)
            if len(str(secret_data['account_number'])) != 8:
                return False
            
            # 계좌상품코드 확인 (2자리)
            if len(str(secret_data['account_product'])) != 2:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Secret validation error: {e}")
            return False
    
    @staticmethod
    def get_real_account_secret(virtual_secret_identifier: str) -> Optional[str]:
        """모의투자 계좌의 실전계좌 참조 경로 반환"""
        try:
            secret_data = SecretLoader.load_secret(virtual_secret_identifier)
            
            if not secret_data.get('is_virtual', False):
                return None  # 실전계좌는 참조 불필요
            
            real_reference = secret_data.get('real_account_reference')
            if real_reference:
                # 환경변수에서 실전계좌 찾기
                real_account = SecretLoader._load_from_env(real_reference)
                if real_account:
                    return real_reference
                
                # 파일에서 실전계좌 찾기 (fallback)
                if virtual_secret_identifier.endswith('.json'):
                    virtual_path = Path(virtual_secret_identifier)
                    real_path = virtual_path.parent / real_reference
                    return str(real_path) if real_path.exists() else None
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get real account reference: {e}")
            return None
    
    @staticmethod
    def list_available_accounts() -> List[str]:
        """사용 가능한 계좌 ID 목록 반환"""
        account_ids = []
        
        # 환경변수에서 계좌 목록
        try:
            if SecretLoader._accounts_cache is None:
                # 캐시 초기화를 위해 더미 로드 시도
                SecretLoader._load_from_env('dummy')
            
            if SecretLoader._accounts_cache:
                account_ids.extend(SecretLoader._accounts_cache.keys())
        except Exception:
            pass
        
        return account_ids
    
    @staticmethod
    def clear_cache():
        """환경변수 캐시 클리어 (테스트용)"""
        SecretLoader._accounts_cache = None