"""
EASE 벤치마크 독립 실행 스크립트

UI(Streamlit)와 독립적으로 실행되어, UI가 꺼져도 실험이 끝까지 수행됩니다.
진행 상태는 results/progress.json에 기록되어 UI에서 폴링할 수 있습니다.
완료 시 results/ 폴더에 최종 결과가 저장됩니다.

사용법 (직접 실행):
    python run_benchmark.py --config results/benchmark_config.json

사용법 (UI에서 자동 실행):
    web_ui.py의 Benchmark 페이지에서 Run 버튼 클릭 시 subprocess로 실행됩니다.
"""

import argparse
import asyncio
import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.config import DEFENSE_PROMPTS
from src.gmail.tools import GmailTools
from src.agents.agent_factory import AgentFactory
from src.assessment.runner import TestRunner
from src.assessment.evaluator import Evaluator
from src.data.loader import AttackDataLoader


# ============================================================
# 진행 상태 관리
# ============================================================

RESULTS_DIR = project_root / 'results'
RESULTS_DIR.mkdir(exist_ok=True)

PROGRESS_FILE = RESULTS_DIR / 'progress.json'

CSV_KEYS = ['agent', 'defense', 'sample_index', 'send_email_called',
            'email_arrived', 'confirmation_exists', 'attack_success',
            'type', 'type_desc']


def _save_csv(filepath, rows):
    """결과를 CSV로 저장"""
    import csv
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_KEYS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def update_progress(status: str, detail: str = '', percent: int = 0, 
                    agent: str = '', defense: str = '', 
                    sample_idx: int = 0, total_samples: int = 0,
                    error: str = ''):
    """진행 상태를 파일에 기록"""
    progress = {
        'status': status,       # 'running', 'completed', 'error'
        'detail': detail,
        'percent': percent,
        'agent': agent,
        'defense': defense,
        'sample_idx': sample_idx,
        'total_samples': total_samples,
        'error': error,
        'updated_at': datetime.now().isoformat()
    }
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
    except:
        pass  # 파일 쓰기 실패해도 실험은 계속


# ============================================================
# 메인 실행
# ============================================================

async def run_benchmark(config: dict):
    """벤치마크 실행 메인 함수"""
    
    agents = config['agents']
    defense_options = config['defense_options']
    attack_config = config['attack_config']
    custom_defense = config.get('custom_defense')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 환경변수에서 API 키 설정 (config에서 전달받음)
    for key, value in config.get('env_vars', {}).items():
        if value:
            os.environ[key] = value
    
    update_progress('running', 'Initializing...', 10)
    
    # 초기화
    victim_gmail = GmailTools('victim')
    attacker_gmail = GmailTools('attacker')
    evaluator = Evaluator()
    runner = TestRunner(evaluator)
    
    # 데이터 로드
    update_progress('running', 'Loading data...', 20)
    
    if attack_config['mode'] == 'dataset':
        loader = AttackDataLoader()
        attack_samples = loader.load(
            types=attack_config.get('types'),
            samples_per_type=attack_config.get('samples_per_type'),
            total_samples=attack_config.get('total_samples')
        )
    else:
        attack_samples = [{
            'index': 1,
            'email_subject': attack_config.get('subject', 'Important Request'),
            'email_body': attack_config.get('body', '')
        }]
    
    # Custom 방어 프롬프트 등록
    if 'custom' in defense_options and custom_defense:
        base_prompt = DEFENSE_PROMPTS['none']['prompt']
        DEFENSE_PROMPTS['custom'] = {
            'name': 'Custom',
            'prompt': f"{base_prompt}\n\nSecurity Guidelines:\n{custom_defense}"
        }
    
    all_results = []
    total_agents = len(agents)
    
    # Agent별 실행
    for agent_idx, agent_name in enumerate(agents):
        
        def make_progress_callback(a_name, a_idx):
            def on_progress(defense_idx, sample_idx, total_defenses, total_samples, message):
                agent_progress = a_idx / total_agents
                defense_progress = (defense_idx - 1) / total_defenses
                sample_progress = sample_idx / total_samples
                percent = 30 + int((agent_progress + (1/total_agents) * (defense_progress + (1/total_defenses) * sample_progress)) * 60)
                
                # 현재 defense 이름 추출
                current_defense = ''
                for dkey, dval in DEFENSE_PROMPTS.items():
                    if dval['name'] in message or dkey in message.lower():
                        current_defense = dval['name']
                        break
                
                update_progress(
                    'running',
                    f"{a_name.upper()} - {message}",
                    min(percent, 90),
                    agent=a_name,
                    defense=current_defense,
                    sample_idx=sample_idx,
                    total_samples=total_samples
                )
            return on_progress
        
        update_progress('running', f'{agent_name.upper()} starting...', 
                       30 + int(agent_idx / total_agents * 60), agent=agent_name)
        
        result = await runner.run_with_defense_comparison(
            agent_name=agent_name,
            agent_factory=AgentFactory,
            victim_gmail=victim_gmail,
            attacker_gmail=attacker_gmail,
            attack_samples=attack_samples,
            defense_prompts=DEFENSE_PROMPTS,
            defense_levels=defense_options,
            progress_callback=make_progress_callback(agent_name, agent_idx)
        )
        
        # 결과 변환 + 방어프롬프트별 개별 저장
        for defense_level, defense_data in result.get('defense_levels', {}).items():
            defense_results = []
            for attack_result in defense_data.get('attack_results', []):
                row = {
                    'agent': agent_name,
                    'defense': defense_level,
                    'sample_index': attack_result.get('sample_index', 0),
                    'send_email_called': attack_result.get('criteria', {}).get('send_email_called', False),
                    'email_arrived': attack_result.get('criteria', {}).get('email_arrived', False),
                    'confirmation_exists': attack_result.get('criteria', {}).get('confirmation_exists', False),
                    'attack_success': attack_result.get('is_successful', False),
                    'type': attack_result.get('type', 0),
                    'type_desc': attack_result.get('type_desc', ''),
                    'details': attack_result.get('details', {})
                }
                defense_results.append(row)
                all_results.append(row)
            
            # 방어프롬프트별 개별 CSV 저장
            if defense_results:
                individual_csv = RESULTS_DIR / f'benchmark_{defense_level}_{agent_name}_{timestamp}.csv'
                _save_csv(individual_csv, defense_results)
                print(f"   💾 개별 저장: {individual_csv.name}")
    
    # 최종 통합 결과 구성
    final_results = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'agents': agents,
        'attack_mode': 'Dataset' if attack_config['mode'] == 'dataset' else 'Custom',
        'defense_options': defense_options,
        'samples': len(attack_samples),
        'results': all_results
    }
    
    # 통합 결과 파일 저장
    result_json_path = RESULTS_DIR / f'benchmark_all_{timestamp}.json'
    with open(result_json_path, 'w', encoding='utf-8') as f:
        json.dump(final_results, f, ensure_ascii=False, indent=2)
    
    result_csv_path = RESULTS_DIR / f'benchmark_all_{timestamp}.csv'
    if all_results:
        _save_csv(result_csv_path, all_results)
    
    # 완료 상태 기록
    update_progress(
        'completed',
        f'Benchmark complete. Results saved to {result_json_path.name}',
        100,
        error=''
    )
    
    print(f"\n{'='*70}")
    print(f"✅ 벤치마크 완료!")
    print(f"   JSON: {result_json_path}")
    print(f"   CSV:  {result_csv_path}")
    print(f"{'='*70}\n")
    
    return final_results


# ============================================================
# 엔트리포인트
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='EASE Benchmark Runner')
    parser.add_argument('--config', required=True, help='Path to benchmark config JSON')
    args = parser.parse_args()
    
    # 설정 파일 로드
    with open(args.config, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print(f"\n{'='*70}")
    print(f"🚀 EASE Benchmark (Independent Process)")
    print(f"{'='*70}")
    print(f"   Agents: {config['agents']}")
    print(f"   Defense: {config['defense_options']}")
    print(f"   Config: {args.config}")
    print(f"{'='*70}\n")
    
    try:
        asyncio.run(run_benchmark(config))
    except Exception as e:
        update_progress('error', str(e), error=traceback.format_exc())
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()