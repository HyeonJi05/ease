"""
send_email 로그를 6개 에이전트 전부에 적용하는 패치 (멱등).

하는 일:
  1) src/agents/base.py 의 EmailAgent 에 공통 헬퍼 _send_email_with_log() 1개 추가
  2) 6개 에이전트(_execute_gmail_tool)의 send_email 분기를 헬퍼 호출 한 줄로 교체
     - gpt / deepseek / o4mini / claude / gemini : 로깅 없던 분기 → 로깅됨
     - llama : 기존 중복 로깅 블록 → 공통 헬퍼로 정리

로그 위치/형식은 기존 llama 로그와 동일:
  results/send_email_log_{agent}.jsonl  (1줄 1 JSON, append)
다만 sample_index / defense 필드를 추가로 기록한다(원래 llama 로그엔 없던 것).
→ 추후 어떤 전송이 어떤 샘플/방어에서 났는지 인자 수준 귀속이 가능.

사용법 (레포 루트 = src/ 가 보이는 곳에서 실행):
    python apply_send_log_patch.py --dry-run   # 미리보기 (파일 변경 없음)
    python apply_send_log_patch.py             # 적용 (원본은 *.bak 으로 백업)
    python apply_send_log_patch.py --revert     # *.bak 에서 원복
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

AGENTS = ["gpt", "deepseek", "o4mini", "claude", "gemini", "llama"]
BASE_PY = Path("src/agents/base.py")
AGENT_DIR = Path("src/agents")
HELPER_MARKER = "_send_email_with_log"

# EmailAgent 클래스에 추가할 공통 헬퍼 (앞 개행 포함, 클래스 메서드 들여쓰기 4칸)
HELPER_CODE = '''
    def _send_email_with_log(self, tool_input):
        """
        send_email 실행 + results/send_email_log_{agent}.jsonl 기록 (전 에이전트 공통).

        - 전송 인자(to/subject/body[:100]/cc/bcc)와 결과를 1줄 JSON으로 append
        - 현재 샘플/방어 조건(GmailTools.current_sample_index / current_defense_level)도 함께 기록
        - 필수 인자 누락 시 KeyError 가 result 의 error 로 기록됨(진단 목적상 의도된 동작)
        """
        import os
        import json
        from datetime import datetime

        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "results")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"send_email_log_{self.get_agent_name()}.jsonl")

        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "agent": self.get_agent_name(),
            "sample_index": getattr(self.gmail, "current_sample_index", None),
            "defense": getattr(self.gmail, "current_defense_level", None),
            "to": tool_input.get("to"),
            "subject": tool_input.get("subject"),
            "body": (tool_input.get("body") or "")[:100],
            "cc": tool_input.get("cc"),
            "bcc": tool_input.get("bcc"),
        }

        try:
            result = self.gmail.send_email(
                to=tool_input["to"],
                subject=tool_input["subject"],
                body=tool_input["body"],
                cc=tool_input.get("cc"),
                bcc=tool_input.get("bcc"),
            )
            log_entry["result"] = result
        except Exception as e:
            result = {"success": False, "error": str(e)}
            log_entry["result"] = result

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\\n")
        except Exception as log_err:
            print(f"send_email 로그 기록 실패: {log_err}")

        return result
'''

# send_email 분기 → trash_email 분기 사이를 통째로 잡아 한 줄 호출로 교체
BRANCH_RE = re.compile(
    r'(?P<indent>[ \t]*)elif tool_name == "send_email":'
    r'.*?'
    r'(?P<tail>\r?\n[ \t]*elif tool_name == "trash_email":)',
    re.DOTALL,
)


def detect_nl(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def patch_base(dry: bool) -> str:
    text = BASE_PY.read_text(encoding="utf-8")
    if HELPER_MARKER in text:
        return "base.py: 이미 헬퍼 있음 → 건너뜀"
    nl = detect_nl(text)
    helper = HELPER_CODE.replace("\n", nl) if nl != "\n" else HELPER_CODE
    new_text = text.rstrip("\r\n") + nl + helper.rstrip("\r\n") + nl
    if not dry:
        shutil.copy2(BASE_PY, str(BASE_PY) + ".bak")
        BASE_PY.write_text(new_text, encoding="utf-8", newline="")
    return "base.py: 헬퍼 _send_email_with_log() 추가"


def patch_agent(name: str, dry: bool) -> str:
    path = AGENT_DIR / f"{name}_agent.py"
    text = path.read_text(encoding="utf-8")
    nl = detect_nl(text)

    def repl(m):
        ind = m.group("indent")
        body_ind = ind + "    "
        return (
            f'{ind}elif tool_name == "send_email":{nl}'
            f"{body_ind}return self._send_email_with_log(tool_input)"
            f'{m.group("tail")}'
        )

    new_text, n = BRANCH_RE.subn(repl, text)
    if n == 0:
        return f"{name}_agent.py: ⚠️ send_email 분기 못 찾음 (수동 확인 필요)"
    if n > 1:
        return f"{name}_agent.py: ⚠️ {n}곳 매칭 (예상 1곳, 수동 확인 필요)"
    if "self._send_email_with_log(tool_input)" in text:
        return f"{name}_agent.py: 이미 헬퍼 호출 중 → 건너뜀"
    if not dry:
        shutil.copy2(path, str(path) + ".bak")
        path.write_text(new_text, encoding="utf-8", newline="")
    return f"{name}_agent.py: send_email 분기 → 헬퍼 호출로 교체"


def revert():
    targets = [BASE_PY] + [AGENT_DIR / f"{n}_agent.py" for n in AGENTS]
    for p in targets:
        bak = Path(str(p) + ".bak")
        if bak.exists():
            shutil.copy2(bak, p)
            print(f"  복원: {p}")
        else:
            print(f"  백업 없음: {p}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="변경 미적용, 미리보기만")
    ap.add_argument("--revert", action="store_true", help="*.bak 에서 원복")
    args = ap.parse_args()

    if not BASE_PY.exists():
        print(f"❌ {BASE_PY} 없음 — 레포 루트에서 실행하세요.")
        sys.exit(1)

    if args.revert:
        print("🔙 원복 중...")
        revert()
        return

    mode = "[DRY-RUN] " if args.dry_run else ""
    print(f"{mode}패치 시작\n" + "-" * 50)
    print("  " + patch_base(args.dry_run))
    for name in AGENTS:
        print("  " + patch_agent(name, args.dry_run))
    print("-" * 50)
    if args.dry_run:
        print("미리보기 완료 (파일 변경 없음). 적용하려면 --dry-run 없이 다시 실행.")
    else:
        print("완료. 원본은 *.bak 으로 백업됨. 문제 시: python apply_send_log_patch.py --revert")


if __name__ == "__main__":
    main()
