"""
추가 모델 merged CSV 3개를 병합하는 스크립트.

사용법:
  python merge_new_models.py merged_o4mini.csv merged_deepseek.csv merged_llama4.csv -o ease_result_new3.csv

이후 기존 ease_result.csv와 합치기:
  python merge_new_models.py ease_result.csv ease_result_new3.csv -o ease_result_all.csv
"""

import pandas as pd
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description="CSV 파일들을 병합합니다.")
    parser.add_argument("files", nargs="+", help="병합할 CSV 파일 경로들")
    parser.add_argument("-o", "--output", required=True, help="출력 파일 경로")
    args = parser.parse_args()

    dfs = []
    for f in args.files:
        try:
            df = pd.read_csv(f, encoding="utf-8-sig")
        except UnicodeDecodeError:
            df = pd.read_csv(f, encoding="cp1252")
        print(f"  {f}: {len(df)}행, agent={df['agent'].unique().tolist()}")
        dfs.append(df)

    merged = pd.concat(dfs, ignore_index=True)
    merged.to_csv(args.output, index=False, encoding="utf-8-sig")

    print(f"\n병합 완료: {args.output}")
    print(f"  총 {len(merged)}행")
    print(f"  agent: {sorted(merged['agent'].unique().tolist())}")
    print(f"  defense: {sorted(merged['defense'].unique().tolist())}")

if __name__ == "__main__":
    main()