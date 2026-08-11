"""
결과 CSV 병합 스크립트

results/ 폴더의 모든 benchmark CSV를 LLM별로 병합합니다.
(agent, defense, sample_index) 기준으로 중복 제거하며, 나중 파일의 결과를 우선합니다.

사용법:
    python merge_results.py

출력:
    results/merged_claude.csv
    results/merged_gpt.csv
    results/merged_gemini.csv
"""

import pandas as pd
import glob
import os

RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'results')

def merge_llm(llm_name):
    """특정 LLM의 모든 결과 CSV를 병합"""
    pattern = os.path.join(RESULTS_DIR, f'*_benchmark_{llm_name}_*.csv')
    files = sorted(glob.glob(pattern))
    
    # stage1_review 파일 제외
    files = [f for f in files if 'stage1_review' not in f and 'merged' not in f]
    
    if not files:
        print(f"  ⚠️ {llm_name}: 결과 파일 없음")
        return None
    
    print(f"\n📂 {llm_name.upper()} — {len(files)}개 파일 발견:")
    for f in files:
        print(f"     {os.path.basename(f)}")
    
    # 모든 CSV 로드 (나중 파일이 뒤에 오도록 정렬됨)
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, encoding='utf-8-sig')
            dfs.append(df)
            print(f"     ✅ {os.path.basename(f)}: {len(df)}건")
        except Exception as e:
            print(f"     ❌ {os.path.basename(f)}: {e}")
    
    if not dfs:
        return None
    
    # 합치기 (나중 파일 우선)
    merged = pd.concat(dfs, ignore_index=True)
    before = len(merged)
    
    # pending 행 제거 (일괄 검증 미완료)
    pending_count = len(merged[merged['confirmation_exists'].astype(str) == 'pending'])
    if pending_count > 0:
        merged = merged[merged['confirmation_exists'].astype(str) != 'pending']
        print(f"     🗑️ pending 행 {pending_count}건 제거")
    
    # 중복 제거: 같은 (agent, defense, sample_index)가 여러 번 있으면 마지막 것만 유지
    merged = merged.drop_duplicates(
        subset=['agent', 'defense', 'sample_index'],
        keep='last'
    )
    after = len(merged)
    
    # 정렬: defense 순서 → sample_index 순서
    defense_order = {'none': 0, 'with_defense': 1, 'data_instruction': 2, 'user_intent': 3}
    merged['_defense_order'] = merged['defense'].map(defense_order).fillna(99)
    merged = merged.sort_values(['_defense_order', 'sample_index']).drop('_defense_order', axis=1)
    merged = merged.reset_index(drop=True)
    
    # 저장
    output_path = os.path.join(RESULTS_DIR, f'merged_{llm_name}.csv')
    merged.to_csv(output_path, index=False, encoding='utf-8-sig')
    
    # 통계
    total_expected = 639 * 4  # 639 샘플 × 4 방어조건
    completion = len(merged) / total_expected * 100
    
    print(f"\n  📊 병합 결과:")
    print(f"     병합 전: {before}건 → 중복 제거 후: {after}건")
    print(f"     진행률: {after}/{total_expected} ({completion:.1f}%)")
    
    # 방어조건별 현황
    for defense in ['none', 'with_defense', 'data_instruction', 'user_intent']:
        count = len(merged[merged['defense'] == defense])
        print(f"     {defense}: {count}/639")
    
    # pending 확인
    pending = len(merged[merged['confirmation_exists'] == 'pending'])
    if pending > 0:
        print(f"     ⚠️ pending 미검증: {pending}건")
    
    print(f"  💾 저장: {output_path}")
    return output_path


def main():
    print(f"{'='*60}")
    print(f"📊 결과 CSV 병합")
    print(f"{'='*60}")
    
    results = {}
    for llm in ['claude', 'gpt', 'gemini', 'o4mini', 'deepseek', 'llama']:
        results[llm] = merge_llm(llm)
    
    print(f"\n{'='*60}")
    print(f"✅ 완료")
    print(f"{'='*60}")
    print(f"\n병합된 파일로 빠진 실험을 이어서 실행:")
    for llm, path in results.items():
        if path:
            print(f"  python run_single_llm.py --llm {llm} --pair N --resume {path}")
    print()


if __name__ == '__main__':
    main()