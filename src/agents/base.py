"""
LLMAgentInterface - 모든 LLM Agent의 추상 기본 클래스

모든 LLM API (Claude, GPT-4o, Gemini, Groq, DeepInfra)를 지원하는 
Agent는 이 인터페이스를 구현해야 합니다.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class EmailAgent(ABC):
    """
    모든 이메일 Agent의 표준 인터페이스
    
    각 Agent (Claude, GPT, Gemini, Groq, DeepInfra)는 
    반드시 이 클래스를 상속받아 구현해야 합니다.
    """
    
    @abstractmethod
    async def process_message(
        self, 
        user_message: str, 
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        사용자 메시지를 처리하고 표준화된 형식으로 반환
        
        Args:
            user_message (str): 사용자의 입력 메시지
            conversation_history (Optional[List[Dict]]): 이전 대화 기록
        
        Returns:
            Dict[str, Any]: 다음 형식의 딕셔너리
            {
                'message': str,                    # 최종 응답 메시지
                'tools_used': List[str],           # 사용된 도구명 (정규화됨, snake_case)
                'conversation': List[Dict],        # 전체 대화 히스토리
                'raw_response': Any,               # 원본 API 응답 (디버깅용)
            }
        
        Raises:
            ValueError: API 키가 없거나 메시지 처리 실패 시
            Exception: API 호출 오류 또는 네트워크 오류
        """
        pass
    
    @abstractmethod
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """
        각 API의 도구 스키마를 반환
        
        Returns:
            List[Dict[str, Any]]: 도구 정의 스키마 (API별 형식)
            
        Note:
            - Claude: Anthropic tool format
            - GPT-4o: OpenAPI function format
            - Gemini: Google tool format
            - Groq: OpenAPI function format
            - DeepInfra: OpenAPI function format
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        현재 Agent가 사용하는 모델명 반환
        
        Returns:
            str: 모델명 (예: "claude-sonnet-4-5-20250929")
        """
        pass
    
    @abstractmethod
    def get_agent_name(self) -> str:
        """
        현재 Agent의 이름 반환 (정규화된 형식)
        
        Returns:
            str: Agent 이름 (예: "claude", "gpt", "gemini", "groq", "deepinfra")
        """
        pass

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
                f.write(json.dumps(log_entry, ensure_ascii=False, default=str) + "\n")
        except Exception as log_err:
            print(f"send_email 로그 기록 실패: {log_err}")

        return result

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
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            print(f"token 로그 기록 실패: {e}")
