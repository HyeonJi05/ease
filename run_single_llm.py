"""
EASE 단일 LLM 벤치마크 실행 스크립트

3개 LLM을 각각 독립된 Gmail 계정 쌍으로 동시 실행하기 위한 스크립트.
각 LLM은 별도의 attacker/victim 계정을 사용하므로 동시 실행 가능.

사용법:
    python run_single_llm.py --llm claude --pair 1
    python run_single_llm.py --llm gpt --pair 2
    python run_single_llm.py --llm gemini --pair 3
    python run_single_llm.py --llm claude --pair 1 --resume results/001_benchmark_claude_20260411.csv

Gmail 계정 쌍 구조:
    pair 1: credentials_victim_1.json / credentials_attacker_1.json
    pair 2: credentials_victim_2.json / credentials_attacker_2.json
    pair 3: credentials_victim_3.json / credentials_attacker_3.json

필요한 파일:
    credentials_victim_{N}.json  - victim Gmail OAuth credentials
    credentials_attacker_{N}.json - attacker Gmail OAuth credentials
    token_victim_{N}.json        - (자동 생성) victim 인증 토큰
    token_attacker_{N}.json      - (자동 생성) attacker 인증 토큰

환경 변수:
    ANTHROPIC_API_KEY  - Claude API 키 (--llm claude 시 필요)
    OPENAI_API_KEY     - OpenAI API 키 (--llm gpt 시 필요)
    GOOGLE_API_KEY     - Gemini API 키 (--llm gemini 시 필요)
"""

import argparse
import asyncio
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# .env 파일에서 환경 변수 로드
from dotenv import load_dotenv
load_dotenv(project_root / '.env')

from src.config import DEFENSE_PROMPTS
from src.gmail.tools import GmailTools
from src.agents.agent_factory import AgentFactory
from src.assessment.runner import TestRunner
from src.assessment.evaluator import Evaluator
from src.data.loader import AttackDataLoader


# ============================================================
# Gmail 계정 쌍 로드
# ============================================================

class GmailToolsWithPair(GmailTools):
    """Gmail 계정 쌍 번호를 지원하는 GmailTools"""
    
    def _load_credentials(self, account_type: str):
        """
        계정 타입 + 쌍 번호로 credentials 로드
        
        account_type 형식: 'victim_1', 'attacker_2' 등
        """
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        
        SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
        
        project_root = Path(__file__).parent
        
        credentials_file = project_root / f'credentials_{account_type}.json'
        token_file = project_root / f'token_{account_type}.json'
        
        creds = None
        
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not credentials_file.exists():
                    raise FileNotFoundError(
                        f"credentials 파일을 찾을 수 없습니다: {credentials_file}\n"
                        f"Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 다운로드하세요.\n"
                        f"파일명: credentials_{account_type}.json"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
        
        return creds


# ============================================================
# 메인 실행
# ============================================================

async def run_single_llm(
    llm_name: str,
    pair_number: int,
    defense_levels: list,
    resume_file: str = None,
    samples_per_type: int = None,
    start: int = None,
    end: int = None
):
    """단일 LLM 벤치마크 실행"""
    
    print(f"\n{'='*70}")
    print(f"🚀 EASE Benchmark - {llm_name.upper()}")
    print(f"{'='*70}")
    print(f"   LLM: {llm_name}")
    print(f"   Gmail 계정 쌍: pair {pair_number}")
    print(f"   방어 조건: {defense_levels}")
    print(f"   샘플 범위: {start or 0} ~ {end or '끝'}")
    print(f"   이어서 실행: {resume_file or '새로 시작'}")
    print(f"{'='*70}\n")
    
    # Gmail 계정 초기화
    victim_type = f'victim_{pair_number}'
    attacker_type = f'attacker_{pair_number}'
    
    print(f"📧 Gmail 계정 초기화 중...")
    print(f"   Victim: credentials_{victim_type}.json")
    print(f"   Attacker: credentials_{attacker_type}.json")
    
    victim_gmail = GmailToolsWithPair(victim_type)
    attacker_gmail = GmailToolsWithPair(attacker_type)
    
    print(f"   ✅ Victim: {victim_gmail.get_email()}")
    print(f"   ✅ Attacker: {attacker_gmail.get_email()}")
    
    # Attacker 이메일 캐시 설정 (에이전트 내부의 placeholder 치환용)
    from src.gmail.tools import GmailTools
    GmailTools._attacker_email_cache = attacker_gmail.get_email()
    print(f"   ✅ Attacker 이메일 캐시: {GmailTools._attacker_email_cache}")
    
    # Evaluator / Runner 초기화
    evaluator = Evaluator()
    runner = TestRunner(evaluator)
    
    # KeyboardInterrupt 시 일괄 검증을 위해 외부 접근 가능하게 저장
    run_single_llm._runner = runner
    run_single_llm._attacker_gmail = attacker_gmail
    
    # 데이터 로드
    print(f"\n📂 공격 데이터 로드 중...")
    loader = AttackDataLoader()
    
    if samples_per_type:
        attack_samples = loader.load(samples_per_type=samples_per_type)
        print(f"   유형별 {samples_per_type}개씩 추출")
    else:
        attack_samples = loader.load()  # 전체 로드
        print(f"   전체 샘플 로드")
    
    # 샘플 범위 슬라이싱
    if start is not None or end is not None:
        total_before = len(attack_samples)
        attack_samples = attack_samples[start:end]
        print(f"   범위 적용: [{start or 0}:{end or total_before}] → {len(attack_samples)}개")
    
    print(f"   총 {len(attack_samples)}개 샘플")
    
    # 벤치마크 실행
    result = await runner.run_with_defense_comparison(
        agent_name=llm_name,
        agent_factory=AgentFactory,
        victim_gmail=victim_gmail,
        attacker_gmail=attacker_gmail,
        attack_samples=attack_samples,
        defense_prompts=DEFENSE_PROMPTS,
        defense_levels=defense_levels,
        resume_file=resume_file
    )
    
    # JSON 결과도 저장
    output_csv = result.get('metadata', {}).get('output_csv', '')
    if output_csv:
        import json
        json_path = output_csv.replace('.csv', '.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        print(f"💾 JSON: {json_path}")
    
    print(f"\n{'='*70}")
    print(f"✅ {llm_name.upper()} 벤치마크 완료!")
    print(f"{'='*70}\n")
    
    return result


# ============================================================
# 엔트리포인트
# ============================================================

def _save_on_interrupt(reason: str):
    """중단/에러 시 일괄 검증 실행 및 결과 저장"""
    import signal
    
    # 일괄 검증 중 Ctrl+C 재발 방지
    original_handler = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    
    print(f"   중간 결과는 results/ 폴더에 저장되어 있습니다.")
    try:
        runner = getattr(run_single_llm, '_runner', None)
        attacker_gmail = getattr(run_single_llm, '_attacker_gmail', None)
        if runner and attacker_gmail and hasattr(runner, '_incremental_rows'):
            print(f"\n🔄 {reason} 전 Stage 3 일괄 검증 + 부가 파일 저장 중...")
            print(f"   ⚠️ 검증 완료까지 잠시 기다려주세요 (Ctrl+C 무시됨)")
            runner._run_batch_verification(
                attacker_gmail,
                runner._incremental_rows,
                runner._output_csv_path
            )
    except Exception as ve:
        print(f"   ⚠️ 일괄 검증 중 오류: {ve}")
    finally:
        signal.signal(signal.SIGINT, original_handler)
    print(f"   --resume 옵션으로 이어서 실행할 수 있습니다.")


def main():
    parser = argparse.ArgumentParser(
        description='EASE 단일 LLM 벤치마크 실행',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  # 컴퓨터 A: 샘플 전반부 (3개 LLM 동시)
  python run_single_llm.py --llm claude --pair 1 --end 320
  python run_single_llm.py --llm gpt --pair 2 --end 320
  python run_single_llm.py --llm gemini --pair 3 --end 320

  # 컴퓨터 B: 샘플 후반부 (3개 LLM 동시)
  python run_single_llm.py --llm claude --pair 4 --start 320
  python run_single_llm.py --llm gpt --pair 5 --start 320
  python run_single_llm.py --llm gemini --pair 6 --start 320

  # 이어서 실행 (중단된 경우)
  python run_single_llm.py --llm claude --pair 1 --end 320 --resume results/001_benchmark_claude_20260411_120000.csv

  # 유형별 10개씩 (테스트용)
  python run_single_llm.py --llm claude --pair 1 --samples-per-type 10
        """
    )
    
    parser.add_argument(
        '--llm', required=True,
        choices=['claude', 'gpt', 'gemini', 'o4mini', 'deepseek', 'llama'],
        help='실행할 LLM 이름'
    )
    parser.add_argument(
        '--pair', required=True, type=int,
        help='Gmail 계정 쌍 번호 (1, 2, 3)'
    )
    parser.add_argument(
        '--defense', nargs='+',
        default=['none', 'with_defense', 'data_instruction', 'user_intent'],
        help='방어 조건 (기본: 4개 전부)'
    )
    parser.add_argument(
        '--resume', default=None,
        help='이어서 실행할 기존 결과 CSV 경로'
    )
    parser.add_argument(
        '--samples-per-type', type=int, default=None,
        help='유형별 샘플 수 (None이면 전체)'
    )
    parser.add_argument(
        '--start', type=int, default=None,
        help='시작 샘플 인덱스 (0-based, 포함)'
    )
    parser.add_argument(
        '--end', type=int, default=None,
        help='끝 샘플 인덱스 (0-based, 미포함)'
    )
    
    args = parser.parse_args()
    
    # API 키 확인
    key_map = {
        'claude': 'ANTHROPIC_API_KEY',
        'gpt': 'OPENAI_API_KEY',
        'gemini': 'GEMINI_API_KEY',
        'o4mini': 'OPENAI_API_KEY',
        'deepseek': 'DEEPSEEK_API_KEY',
        'llama': 'TOGETHER_API_KEY',
    }
    
    required_key = key_map[args.llm]
    if not os.environ.get(required_key):
        print(f"⚠️ 환경 변수 {required_key}가 설정되지 않았습니다.")
        print(f"   export {required_key}=your-api-key")
        sys.exit(1)
    
    # 실행
    try:
        asyncio.run(run_single_llm(
            llm_name=args.llm,
            pair_number=args.pair,
            defense_levels=args.defense,
            resume_file=args.resume,
            samples_per_type=args.samples_per_type,
            start=args.start,
            end=args.end
        ))
    except KeyboardInterrupt:
        print(f"\n\n⚠️ 사용자에 의해 중단되었습니다.")
        _save_on_interrupt("중단")
        sys.exit(0)
    except SystemExit as e:
        print(f"\n\n🚫 실험 중단: {e}")
        _save_on_interrupt("한도 초과")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        _save_on_interrupt("에러")
        sys.exit(1)


if __name__ == '__main__':
    main()