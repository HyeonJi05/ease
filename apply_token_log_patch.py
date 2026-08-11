"""
LLM 토큰(usage) 로깅을 6개 에이전트 전부에 적용하는 패치 (멱등).

하는 일:
  1) src/agents/base.py 의 EmailAgent 에 공통 헬퍼 _log_token_usage(response, sdk) 추가
  2) 각 에이전트의 API 응답 직후에 한 줄(self._log_token_usage(response, '<sdk>')) 삽입
     - chat.completions.create  → 'openai'   (gpt/deepseek/o4mini/llama)
     - messages.create          → 'anthropic'(claude)
     - asyncio.to_thread(chat.send_message,...) → 'gemini'  (호출 2곳 모두)

기록: results/token_log_{agent}.jsonl  (API 호출 1건당 1줄)
  {timestamp, agent, sample_index, defense, prompt_tokens, completion_tokens}
  → 사후에 (sample_index, defense)로 합산하면 샘플당 토큰, 평균내면 샘플당 평균 토큰.

설계 메모:
  - 에이전트 파일은 이름이 아니라 src/agents/*_agent.py 글롭 + 내용으로 탐지 (llama4→llama rename 무관)
  - 토큰 로깅 실패가 실험을 절대 중단시키지 않도록 전 구간 try/except·getattr 가드
  - 멱등: 이미 적용된 파일은 건너뜀

사용법 (레포 루트에서):
    python apply_token_log_patch.py --dry-run
    python apply_token_log_patch.py
    python apply_token_log_patch.py --revert
"""
import argparse
import glob
import re
import shutil
import sys
from pathlib import Path

BASE_PY = Path("src/agents/base.py")
HELPER_MARKER = "_log_token_usage"

HELPER_CODE = '''
    def _log_token_usage(self, response, sdk):
        """
        API 응답의 토큰(usage)을 results/token_log_{agent}.jsonl 에 호출 1건당 1줄 기록.
        sdk: 'openai' | 'anthropic' | 'gemini'. 실패해도 실험을 중단시키지 않는다.
        """
        import os
        import json
        from datetime import datetime

        pt = ct = None
        try:
            if sdk == "openai":
                u = getattr(response, "usage", None)
                pt = getattr(u, "prompt_tokens", None) if u else None
                ct = getattr(u, "completion_tokens", None) if u else None
            elif sdk == "anthropic":
                u = getattr(response, "usage", None)
                pt = getattr(u, "input_tokens", None) if u else None
                ct = getattr(u, "output_tokens", None) if u else None
            elif sdk == "gemini":
                u = getattr(response, "usage_metadata", None)
                pt = getattr(u, "prompt_token_count", None) if u else None
                ct = getattr(u, "candidates_token_count", None) if u else None
        except Exception:
            pt = ct = None

        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.get_agent_name(),
            "sample_index": getattr(self.gmail, "current_sample_index", None),
            "defense": getattr(self.gmail, "current_defense_level", None),
            "prompt_tokens": pt,
            "completion_tokens": ct,
        }
        try:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"token_log_{self.get_agent_name()}.jsonl")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\\n")
        except Exception as e:
            print(f"token 로그 기록 실패: {e}")
'''

# create() / to_thread() 인자에 중첩 괄호가 없어 .*? 비탐욕 매칭이 안전
RE_OPENAI = re.compile(
    r'(?P<ind>[ \t]*)response = (?:await )?self\.client\.chat\.completions\.create\(.*?\)',
    re.DOTALL,
)
RE_ANTHROPIC = re.compile(
    r'(?P<ind>[ \t]*)response = (?:await )?self\.client\.messages\.create\(.*?\)',
    re.DOTALL,
)
RE_GEMINI = re.compile(
    r'(?P<ind>[ \t]*)response = (?:await )?asyncio\.to_thread\(\s*chat\.send_message,.*?\)',
    re.DOTALL,
)


def detect_nl(text):
    return "\r\n" if "\r\n" in text else "\n"


def patch_base(dry):
    text = BASE_PY.read_text(encoding="utf-8")
    if HELPER_MARKER in text:
        return "base.py: 이미 헬퍼 있음 → 건너뜀"
    nl = detect_nl(text)
    helper = HELPER_CODE.replace("\n", nl) if nl != "\n" else HELPER_CODE
    new_text = text.rstrip("\r\n") + nl + helper.rstrip("\r\n") + nl
    if not dry:
        shutil.copy2(BASE_PY, str(BASE_PY) + ".tokbak")
        BASE_PY.write_text(new_text, encoding="utf-8", newline="")
    return "base.py: 헬퍼 _log_token_usage() 추가"


def patch_agent(path, dry):
    text = Path(path).read_text(encoding="utf-8")
    name = Path(path).name
    if "self._log_token_usage(response" in text:
        return f"{name}: 이미 적용됨 → 건너뜀"

    # SDK 탐지 (내용 기반)
    if "asyncio.to_thread" in text and "send_message" in text:
        sdk, rx = "gemini", RE_GEMINI
    elif "messages.create" in text:
        sdk, rx = "anthropic", RE_ANTHROPIC
    elif "chat.completions.create" in text:
        sdk, rx = "openai", RE_OPENAI
    else:
        return f"{name}: API 호출 없음 → 건너뜀"

    nl = detect_nl(text)

    def repl(m):
        ind = m.group("ind")
        return f'{m.group(0)}{nl}{ind}self._log_token_usage(response, "{sdk}")'

    new_text, n = rx.subn(repl, text)
    if n == 0:
        return f"{name}: ⚠️ {sdk} 호출 패턴 못 찾음 (수동 확인 필요)"
    if not dry:
        shutil.copy2(path, str(path) + ".tokbak")
        Path(path).write_text(new_text, encoding="utf-8", newline="")
    return f"{name}: [{sdk}] 응답 직후 토큰 로깅 {n}곳 삽입"


def revert():
    targets = [BASE_PY] + [Path(p) for p in glob.glob("src/agents/*_agent.py")]
    for p in targets:
        bak = Path(str(p) + ".tokbak")
        if bak.exists():
            shutil.copy2(bak, p)
            print(f"  복원: {p}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()

    if not BASE_PY.exists():
        print(f"❌ {BASE_PY} 없음 — 레포 루트에서 실행하세요.")
        sys.exit(1)

    if args.revert:
        print("🔙 토큰 패치 원복 중...")
        revert()
        return

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(f"{mode}토큰 로깅 패치 시작\n" + "-" * 55)
    print("  " + patch_base(args.dry_run))
    for path in sorted(glob.glob("src/agents/*_agent.py")):
        print("  " + patch_agent(path, args.dry_run))
    print("-" * 55)
    if args.dry_run:
        print("미리보기 완료. 적용하려면 --dry-run 없이 다시 실행.")
    else:
        print("완료. 원본은 *.tokbak 백업. 원복: python apply_token_log_patch.py --revert")


if __name__ == "__main__":
    main()
