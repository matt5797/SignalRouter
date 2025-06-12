#!/usr/bin/env python3
"""
환경변수 설정 생성기
secrets 폴더의 JSON 파일들을 읽어서 ACCOUNTS_CONFIG 환경변수를 생성
"""

import json
import os
import sys
from pathlib import Path
from typing import List, Dict


def load_secret_files(secrets_dir: str = "secrets") -> List[Dict]:
    """secrets 폴더의 모든 JSON 파일을 로드"""
    secrets_path = Path(secrets_dir)
    
    if not secrets_path.exists():
        print(f"❌ Error: {secrets_dir} directory not found")
        return []
    
    accounts = []
    json_files = list(secrets_path.glob("*.json"))
    
    if not json_files:
        print(f"❌ No JSON files found in {secrets_dir}")
        return []
    
    print(f"📁 Found {len(json_files)} JSON files in {secrets_dir}")
    
    for json_file in json_files:
        try:
            # 파일명에서 계좌 ID 추출 (확장자 제거)
            account_id = json_file.stem
            
            # JSON 파일 로드
            with open(json_file, 'r', encoding='utf-8') as f:
                account_data = json.load(f)
            
            # 계좌 ID 추가
            account_data['id'] = account_id
            
            # 필수 필드 검증
            required_fields = ['app_key', 'app_secret', 'account_number', 'account_product']
            missing_fields = [field for field in required_fields if field not in account_data]
            
            if missing_fields:
                print(f"⚠️  Warning: {json_file.name} missing fields: {missing_fields}")
                continue
            
            accounts.append(account_data)
            print(f"✅ Loaded: {account_id} ({'Virtual' if account_data.get('is_virtual', False) else 'Real'})")
            
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing {json_file.name}: {e}")
        except Exception as e:
            print(f"❌ Error loading {json_file.name}: {e}")
    
    return accounts


def generate_env_config(accounts: List[Dict]) -> str:
    """계좌 목록을 환경변수용 JSON 문자열로 변환"""
    if not accounts:
        return ""
    
    # 민감정보 제거용 필드 (선택사항)
    # 필요시 주석 해제하여 로그에서 민감정보 제거
    # for account in accounts:
    #     account.pop('app_secret', None)  # 시크릿 제거
    
    # 압축된 JSON 생성 (공백 제거)
    json_str = json.dumps(accounts, separators=(',', ':'), ensure_ascii=False)
    return json_str


def save_to_file(env_config: str, output_file: str = ".env.accounts"):
    """환경변수를 파일로 저장"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(f"ACCOUNTS_CONFIG='{env_config}'\n")
        print(f"💾 Environment config saved to: {output_file}")
        print(f"📏 Config size: {len(env_config)} characters")
    except Exception as e:
        print(f"❌ Error saving to file: {e}")


def print_usage():
    """사용법 출력"""
    print("""
🔧 Environment Config Generator

Usage:
    python generate_env_config.py [options]

Options:
    --secrets-dir DIR    Secrets directory (default: secrets)
    --output-file FILE   Output file (default: .env.accounts)
    --print-only         Print to stdout without saving to file
    --help               Show this help

Examples:
    python generate_env_config.py
    python generate_env_config.py --secrets-dir ./my_secrets
    python generate_env_config.py --print-only
    """)


def main():
    """메인 실행 함수"""
    # 명령줄 인수 파싱 (간단하게)
    args = sys.argv[1:]
    
    secrets_dir = "secrets"
    output_file = ".env.accounts"
    print_only = False
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg in ['--help', '-h']:
            print_usage()
            return
        elif arg == '--secrets-dir' and i + 1 < len(args):
            secrets_dir = args[i + 1]
            i += 1
        elif arg == '--output-file' and i + 1 < len(args):
            output_file = args[i + 1]
            i += 1
        elif arg == '--print-only':
            print_only = True
        else:
            print(f"❌ Unknown argument: {arg}")
            print_usage()
            return
        
        i += 1
    
    print("🚀 SignalRouter Environment Config Generator")
    print("=" * 50)
    
    # 1. 계좌 파일들 로드
    accounts = load_secret_files(secrets_dir)
    
    if not accounts:
        print("❌ No valid accounts found. Exiting.")
        return
    
    print(f"\n📊 Summary:")
    print(f"   Total accounts: {len(accounts)}")
    
    virtual_count = sum(1 for acc in accounts if acc.get('is_virtual', False))
    real_count = len(accounts) - virtual_count
    print(f"   Real accounts: {real_count}")
    print(f"   Virtual accounts: {virtual_count}")
    
    # 2. 환경변수 생성
    env_config = generate_env_config(accounts)
    
    if not env_config:
        print("❌ Failed to generate environment config")
        return
    
    # 3. 출력 또는 저장
    if print_only:
        print(f"\n📤 Environment Variable:")
        print("-" * 50)
        print(f"ACCOUNTS_CONFIG='{env_config}'")
        print("-" * 50)
    else:
        save_to_file(env_config, output_file)
        print(f"\n✅ Done! Copy the content of {output_file} to your Railway environment variables.")
    
    # 4. 크기 경고
    if len(env_config) > 30000:  # Railway 제한 근처
        print("⚠️  Warning: Config size is approaching Railway's 32KB limit!")
    
    print("\n💡 Next steps:")
    print("   1. Copy the ACCOUNTS_CONFIG value to Railway environment variables")
    print("   2. Deploy your application")
    print("   3. Remove local secrets files from production (keep backups!)")


if __name__ == "__main__":
    main()