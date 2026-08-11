"""
Gmail OAuth 토큰 생성 스크립트

각 Gmail 계정에 대해 최초 OAuth 인증을 수행하여 token 파일을 생성합니다.
실행 시 브라우저가 열리며, Google 계정 로그인 후 권한을 승인하면 토큰이 저장됩니다.

사용법:
    # pair 1의 victim 계정 인증
    python setup_gmail_tokens.py --pair 1 --role victim

    # pair 1의 attacker 계정 인증
    python setup_gmail_tokens.py --pair 1 --role attacker

    # pair 1의 victim + attacker 둘 다
    python setup_gmail_tokens.py --pair 1

    # pair 1~3 전부 한 번에
    python setup_gmail_tokens.py --pair 1 2 3
"""

import argparse
import sys
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
PROJECT_ROOT = Path(__file__).parent


def authenticate(pair: int, role: str):
    """단일 계정 OAuth 인증"""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    account_type = f"{role}_{pair}"
    credentials_file = PROJECT_ROOT / f"credentials_{account_type}.json"
    token_file = PROJECT_ROOT / f"token_{account_type}.json"
    
    print(f"\n{'─'*50}")
    print(f"📧 {account_type}")
    print(f"   credentials: {credentials_file.name}")
    print(f"   token:       {token_file.name}")
    
    # credentials 파일 확인
    if not credentials_file.exists():
        print(f"   ❌ credentials 파일이 없습니다!")
        print(f"   → {credentials_file} 를 배치해주세요.")
        return False
    
    # 기존 토큰 확인
    if token_file.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            if creds and creds.valid:
                print(f"   ✅ 이미 유효한 토큰이 존재합니다.")
                return True
            elif creds and creds.expired and creds.refresh_token:
                print(f"   🔄 토큰 갱신 중...")
                creds.refresh(Request())
                with open(token_file, 'w') as f:
                    f.write(creds.to_json())
                print(f"   ✅ 토큰 갱신 완료")
                return True
        except Exception as e:
            print(f"   ⚠️ 기존 토큰 로드 실패: {e}")
    
    # 새로 인증
    print(f"   🌐 브라우저에서 Google 계정으로 로그인해주세요...")
    print(f"   ⚠️ {role}_{pair} 에 해당하는 Gmail 계정으로 로그인하세요!")
    
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            str(credentials_file), SCOPES
        )
        creds = flow.run_local_server(port=0)
        
        with open(token_file, 'w') as f:
            f.write(creds.to_json())
        
        print(f"   ✅ 토큰 생성 완료: {token_file.name}")
        return True
    except Exception as e:
        print(f"   ❌ 인증 실패: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Gmail OAuth 토큰 생성',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python setup_gmail_tokens.py --pair 1              # pair 1 (victim + attacker)
  python setup_gmail_tokens.py --pair 1 --role victim # pair 1의 victim만
  python setup_gmail_tokens.py --pair 1 2 3           # pair 1~3 전부
  python setup_gmail_tokens.py --pair 1 2 3 4 5 6     # pair 1~6 전부
        """
    )
    parser.add_argument(
        '--pair', nargs='+', type=int, required=True,
        help='Gmail 계정 쌍 번호 (예: 1 2 3)'
    )
    parser.add_argument(
        '--role', choices=['victim', 'attacker'],
        help='특정 역할만 인증 (미지정 시 둘 다)'
    )
    args = parser.parse_args()
    
    roles = [args.role] if args.role else ['victim', 'attacker']
    
    print(f"\n{'='*50}")
    print(f"🔐 Gmail OAuth 토큰 생성")
    print(f"{'='*50}")
    print(f"   Pair: {args.pair}")
    print(f"   Role: {roles}")
    
    results = {}
    for pair in args.pair:
        for role in roles:
            key = f"{role}_{pair}"
            results[key] = authenticate(pair, role)
    
    # 요약
    print(f"\n{'='*50}")
    print(f"📊 결과")
    print(f"{'='*50}")
    for key, success in results.items():
        status = "✅ 완료" if success else "❌ 실패"
        print(f"   {key}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\n   {passed}/{total} 완료")
    print(f"{'='*50}\n")


if __name__ == '__main__':
    main()