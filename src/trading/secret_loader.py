"""
SecretLoader - KIS API 인증 정보 로드 유틸리티
Secret 파일에서 계좌 정보를 안전하게 로드하는 기능 제공
"""

import json
from pathlib import Path
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SecretLoader:
    """계좌 비밀 정보 로더"""
    
    @staticmethod
    def load_secret(secret_file_path: str) -> Dict:
        """Secret 파일에서 계좌 정보 로드"""
        try:
            file_path = Path(secret_file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Secret file not found: {secret_file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                secret_data = json.load(f)
            
            # 필수 필드 검증
            required_fields = ['app_key', 'app_secret', 'account_number', 'account_product']
            missing_fields = [field for field in required_fields if field not in secret_data]
            
            if missing_fields:
                raise ValueError(f"Missing required fields in secret file: {missing_fields}")
            
            logger.debug(f"Secret loaded from {secret_file_path}")
            return secret_data
            
        except Exception as e:
            logger.error(f"Failed to load secret from {secret_file_path}: {e}")
            raise
    
    @staticmethod
    def validate_secret(secret_data: Dict) -> bool:
        """Secret 데이터 유효성 검증"""
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
    def get_real_account_secret(virtual_secret_path: str) -> Optional[str]:
        """모의투자 계좌의 실전계좌 참조 경로 반환"""
        try:
            secret_data = SecretLoader.load_secret(virtual_secret_path)
            
            if not secret_data.get('is_virtual', False):
                return None  # 실전계좌는 참조 불필요
            
            real_reference = secret_data.get('real_account_reference')
            if real_reference:
                # 같은 폴더에서 실전계좌 파일 찾기
                virtual_path = Path(virtual_secret_path)
                real_path = virtual_path.parent / real_reference
                return str(real_path) if real_path.exists() else None
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to get real account reference: {e}")
            return None
