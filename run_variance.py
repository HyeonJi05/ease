"""
EASE 분산 분석 러너 (R1-2 대응)

목적:
  T=1.0 확률적 디코딩 하에서 "동일 입력을 반복했을 때 cell(=LLM×방어)의 ASR이
  얼마나 흔들리는지(run-to-run 변동)"를 부분집합에서 측정한다.
  ⚠️ 본문 표의 ASR을 재현/검증하는 게 아니다. 전체(639) 대비 극히 일부(고정 12개)에서
     디코딩 변동만 분리해 보는 것이므로, 여기 수치가 본문 cell ASR과 일치할 의무는 없다.

기존 코드 재사용 (수정 0):
  - run_single_llm.GmailToolsWithPair  (계정 쌍 로딩)
  - src.assessment.runner.TestRunner.run_with_defense_comparison  (평가 본체)
  - src.assessment.evaluator.Evaluator / src.agents.agent_factory.AgentFactory
  - src.config.DEFENSE_PROMPTS / src.data.loader.AttackDataLoader

이 모듈이 새로 하는 일은 딱 셋:
  1) 샘플 고정  : 유형당 N개(기본 2) 유형 내 무작위 + 시드 고정 → JSON에 박아 재사용
                  (모든 cell·모든 반복이 동일 샘플 사용 → 샘플 선택 변동 제거, 디코딩 변동만 분리)
  2) 반복       : (agent × defense) 각 cell을 reps회(기본 3) 반복 실행
  3) 집계       : cell별 ASR을 평균±표준편차(ddof=1)·min·max로 보고

ASR 집계는 반환 객체가 아니라 각 호출이 저장한 결과 CSV(metadata.output_csv)를 읽어서 낸다.
(Stage 3 일괄검증이 끝난 최종 attack_success 가 CSV에만 반영되기 때문)

사용 예:
  # 파일럿: 한 cell만 3회 (gpt × D0)
  python run_variance.py --agents gpt --defenses none --reps 3 --pair 1

  # 파일럿에서 단순 무작위 추출도 같이 보기 (별도 고정 파일)
  python run_variance.py --agents gpt --defenses none --reps 3 --pair 1 --sampling random --total 12

  # 전체 sweep (6 LLM × 4 방어, 각 3회)
  python run_variance.py --reps 3 --pair 1

실행 위치: 레포 루트 (src/ 가 보이는 곳)
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import csv as _csv
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── 기존 모듈 재사용 ──
from src.config import DEFENSE_PROMPTS
from src.agents.agent_factory import AgentFactory
from src.assessment.runner import TestRunner
from src.assessment.evaluator import Evaluator
from src.data.loader import AttackDataLoader
from src.gmail.tools import GmailTools
from run_single_llm import GmailToolsWithPair  # 계정 쌍 로더 재사용

# 방어 별칭 (D0~D3 → 내부 키)
DEFENSE_ALIASES = {
    "d0": "none", "d1": "with_defense", "d2": "data_instruction", "d3": "user_intent",
    "none": "none", "with_defense": "with_defense",
    "data_instruction": "data_instruction", "user_intent": "user_intent",
}
ALL_DEFENSES = ["none", "with_defense", "data_instruction", "user_intent"]
ALL_AGENTS = ["claude", "gpt", "gemini", "o4mini", "deepseek", "llama"]


# ============================================================
# 1) 샘플 고정  (Gmail/API 불필요 — 독립 테스트 가능)
# ============================================================

def build_fixed_samples(per_type=2, seed=42, sampling="stratified", total=12):
    """
    고정 샘플 dict 리스트 반환. dict 형식은 loader._load_csv() 와 동일하므로
    runner 가 attack_sample.get('index') 로 원본 행번호를 그대로 읽는다.

    sampling="stratified": 유형당 per_type 개를 유형 내 무작위(시드 고정)로 추출
    sampling="random"    : 전체에서 total 개를 무작위(시드 고정) 추출
    반환: (samples, meta)
    """
    loader = AttackDataLoader()
    all_attacks = loader._load_csv()  # 각 dict 에 원본 'index'(0-based 행번호)와 'type' 포함
    rng = random.Random(seed)

    if sampling == "stratified":
        by_type = {}
        for a in all_attacks:
            by_type.setdefault(a["type"], []).append(a)
        chosen = []
        for t in sorted(by_type):
            pool = by_type[t]
            k = min(per_type, len(pool))
            chosen.extend(rng.sample(pool, k))
    elif sampling == "random":
        chosen = rng.sample(all_attacks, min(total, len(all_attacks)))
    else:
        raise ValueError(f"알 수 없는 sampling: {sampling}")

    # 인덱스 기준 정렬(안정성). 원본 'index' 는 절대 재할당하지 않는다.
    chosen.sort(key=lambda a: a["index"])

    meta = {
        "seed": seed,
        "sampling": sampling,
        "per_type": per_type if sampling == "stratified" else None,
        "total": total if sampling == "random" else len(chosen),
        "indices": [a["index"] for a in chosen],
        "by_type": {},
    }
    for a in chosen:
        meta["by_type"].setdefault(str(a["type"]), []).append(a["index"])
    return chosen, meta


def load_or_create_fixed(samples_file, per_type, seed, sampling, total, refresh):
    """고정 샘플을 JSON에 박아두고 재사용. 있으면 그 인덱스 그대로 복원."""
    path = Path(samples_file)
    loader = AttackDataLoader()
    all_attacks = loader._load_csv()
    by_index = {a["index"]: a for a in all_attacks}

    if path.exists() and not refresh:
        meta = json.loads(path.read_text(encoding="utf-8"))
        samples = [by_index[i] for i in meta["indices"]]
        print(f"📌 고정 샘플 재사용: {path.name}  ({len(samples)}개, 시드 {meta.get('seed')})")
        return samples, meta

    samples, meta = build_fixed_samples(per_type, seed, sampling, total)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"📌 고정 샘플 생성·저장: {path.name}  ({len(samples)}개)")
    return samples, meta


# ============================================================
# 2) 반복 + 3) 집계
# ============================================================

def _to_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1")


def asr_from_csv(csv_path, agent, defense, n_expected):
    """저장된 결과 CSV에서 (agent, defense) cell 의 ASR(%) 계산. (최종 attack_success 기준)"""
    n_success = 0
    n_rows = 0
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        for row in _csv.DictReader(f):
            if row.get("agent") == agent and row.get("defense") == defense:
                n_rows += 1
                if _to_bool(row.get("attack_success", False)):
                    n_success += 1
    asr = 100.0 * n_success / n_expected if n_expected else 0.0
    return asr, n_success, n_rows


async def run_one_rep(agent, defenses, samples, victim, attacker):
    """한 번의 (agent, 모든 defenses) 실행 → 저장된 결과 CSV 경로 반환."""
    evaluator = Evaluator()
    runner = TestRunner(evaluator)
    result = await runner.run_with_defense_comparison(
        agent_name=agent,
        agent_factory=AgentFactory,
        victim_gmail=victim,
        attacker_gmail=attacker,
        attack_samples=samples,
        defense_prompts=DEFENSE_PROMPTS,
        defense_levels=defenses,
        resume_file=None,
    )
    return result.get("metadata", {}).get("output_csv", "")


async def main_async(args):
    agents = args.agents or ALL_AGENTS
    defenses = [DEFENSE_ALIASES[d.lower()] for d in (args.defenses or ALL_DEFENSES)]
    n_expected = None  # 고정 샘플 개수로 설정됨

    # ── 고정 샘플 ──
    samples, sample_meta = load_or_create_fixed(
        args.samples_file, args.per_type, args.seed, args.sampling, args.total, args.refresh
    )
    n_expected = len(samples)

    print(f"\n{'='*70}")
    print(f"🔁 EASE 분산 분석")
    print(f"{'='*70}")
    print(f"   에이전트 : {agents}")
    print(f"   방어     : {defenses}")
    print(f"   반복(reps): {args.reps}")
    print(f"   고정 샘플 : {n_expected}개 ({args.sampling}, 시드 {args.seed})  유형분포={sample_meta['by_type']}")
    print(f"   계정 쌍   : pair {args.pair}")
    print(f"   총 cell-실행: {len(agents)} × {len(defenses)} × {args.reps} "
          f"= {len(agents)*len(defenses)*args.reps}  (cell당 샘플 {n_expected}개)")
    print(f"{'='*70}\n")

    # ── Gmail 계정 (run_single_llm 과 동일 방식) ──
    victim = GmailToolsWithPair(f"victim_{args.pair}")
    attacker = GmailToolsWithPair(f"attacker_{args.pair}")
    GmailTools._attacker_email_cache = attacker.get_email()  # placeholder 치환용
    print(f"📧 victim={victim.get_email()}  attacker={attacker.get_email()}")
    print(f"📧 attacker 캐시={GmailTools._attacker_email_cache}\n")

    # raw: (agent, defense, rep) 별 ASR 기록
    raw_rows = []  # dict: agent, defense, rep, n_expected, n_success, n_rows, asr, run_csv
    cell_asrs = {}  # (agent, defense) -> [asr, ...]

    for agent in agents:
        for rep in range(1, args.reps + 1):
            print(f"\n{'─'*70}\n▶ {agent.upper()}  rep {rep}/{args.reps}\n{'─'*70}")
            try:
                run_csv = await run_one_rep(agent, defenses, samples, victim, attacker)
            except Exception as e:
                import traceback
                print(f"  ⚠️ rep 실행 오류: {e}")
                traceback.print_exc()
                for d in defenses:
                    raw_rows.append({
                        "agent": agent, "defense": d, "rep": rep,
                        "n_expected": n_expected, "n_success": "", "n_rows": "",
                        "asr": "", "run_csv": "ERROR",
                    })
                continue

            for d in defenses:
                asr, n_success, n_rows = asr_from_csv(run_csv, agent, d, n_expected)
                if n_rows != n_expected:
                    print(f"  ⚠️ {agent}×{d}: 결과행 {n_rows}개 (기대 {n_expected}개) — 일부 누락 가능")
                raw_rows.append({
                    "agent": agent, "defense": d, "rep": rep,
                    "n_expected": n_expected, "n_success": n_success, "n_rows": n_rows,
                    "asr": round(asr, 2), "run_csv": Path(run_csv).name if run_csv else "",
                })
                cell_asrs.setdefault((agent, d), []).append(asr)
                print(f"  · {agent}×{d}: ASR {asr:.1f}%  ({n_success}/{n_expected})")

    # ── 집계 ──
    summary_rows = []
    for (agent, d), asrs in cell_asrs.items():
        mean = statistics.mean(asrs) if asrs else 0.0
        std = statistics.stdev(asrs) if len(asrs) >= 2 else 0.0
        summary_rows.append({
            "agent": agent, "defense": d, "n_reps": len(asrs),
            "mean_asr": round(mean, 2), "std_asr": round(std, 2),
            "min_asr": round(min(asrs), 2) if asrs else 0.0,
            "max_asr": round(max(asrs), 2) if asrs else 0.0,
            "asrs": ";".join(f"{a:.1f}" for a in asrs),
        })
    summary_rows.sort(key=lambda r: (ALL_AGENTS.index(r["agent"]) if r["agent"] in ALL_AGENTS else 99,
                                     ALL_DEFENSES.index(r["defense"]) if r["defense"] in ALL_DEFENSES else 99))

    # ── 저장 ──
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("results"); out_dir.mkdir(exist_ok=True)
    raw_path = out_dir / f"variance_raw_runs_{ts}.csv"
    sum_path = out_dir / f"variance_summary_{ts}.csv"

    with open(raw_path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.DictWriter(f, fieldnames=["agent", "defense", "rep", "n_expected",
                                           "n_success", "n_rows", "asr", "run_csv"])
        w.writeheader(); w.writerows(raw_rows)
    with open(sum_path, "w", newline="", encoding="utf-8-sig") as f:
        w = _csv.DictWriter(f, fieldnames=["agent", "defense", "n_reps", "mean_asr",
                                           "std_asr", "min_asr", "max_asr", "asrs"])
        w.writeheader(); w.writerows(summary_rows)

    # ── 콘솔 표 ──
    print(f"\n{'='*70}\n📊 cell별 ASR 평균 ± 표준편차 (reps={args.reps}, n={n_expected})\n{'='*70}")
    print(f"{'agent':10}{'defense':18}{'mean±std':>16}{'range':>16}")
    for r in summary_rows:
        rng = f"{r['min_asr']:.0f}~{r['max_asr']:.0f}"
        mstd = f"{r['mean_asr']:.1f} ± {r['std_asr']:.1f}"
        print(f"{r['agent']:10}{r['defense']:18}{mstd:>16}{rng:>16}")
    print(f"\n💾 raw    : {raw_path}")
    print(f"💾 summary: {sum_path}")
    print(f"💾 고정샘플: {args.samples_file}")
    print("\n※ 이 수치는 부분집합(고정 12개)의 run-to-run 변동이며, 본문 표 ASR의 재현/검증이 아님.")


def main():
    ap = argparse.ArgumentParser(
        description="EASE 분산 분석 러너 (기존 평가 코드 재사용)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--agents", nargs="+", default=None,
                    help=f"대상 에이전트 (기본 전체: {ALL_AGENTS})")
    ap.add_argument("--defenses", nargs="+", default=None,
                    help="방어 (none/with_defense/data_instruction/user_intent 또는 D0~D3, 기본 전체)")
    ap.add_argument("--reps", type=int, default=3, help="cell당 반복 횟수 (기본 3)")
    ap.add_argument("--pair", type=int, default=1, help="Gmail 계정 쌍 번호 (기본 1)")
    ap.add_argument("--seed", type=int, default=42, help="샘플 추출 시드 (기본 42)")
    ap.add_argument("--per-type", type=int, default=2, dest="per_type",
                    help="stratified: 유형당 샘플 수 (기본 2 → 6유형×2=12)")
    ap.add_argument("--sampling", choices=["stratified", "random"], default="stratified",
                    help="stratified(유형균등) | random(단순무작위)")
    ap.add_argument("--total", type=int, default=12, help="random 모드 총 샘플 수 (기본 12)")
    ap.add_argument("--samples-file", default=None, dest="samples_file",
                    help="고정 샘플 JSON 경로 (기본: sampling 따라 자동)")
    ap.add_argument("--refresh", action="store_true", help="고정 샘플 재생성(기존 JSON 무시)")
    args = ap.parse_args()

    if args.samples_file is None:
        args.samples_file = f"variance_samples_{args.sampling}.json"

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
