"""
Custom Agent Example
EmailAgent를 상속하여 자신만의 LLM 에이전트를 구현하는 예제

이 파일을 src/agents/ 폴더에 복사하고 수정하여 사용하세요.
"""

from typing import List, Dict, Any

from .base import EmailAgent
from .tool_name_mapper import ToolNameMapper
from src.config import DEFENSE_PROMPTS


class MyAgent(EmailAgent):
    """
    사용자 정의 LLM 에이전트 예제
    
    필수 구현 메서드:
    - __init__(): 초기화
    - get_tools_schema(): 도구 스키마 반환
    - get_provider_name(): 제공자 이름 반환
    - get_model_name(): 모델 이름 반환
    - process_message(): 메시지 처리 (핵심 로직)
    """
    
    def __init__(self, api_key: str, gmail_tools, system_prompt: str = None):
        """
        에이전트 초기화
        
        Args:
            api_key: LLM API 키
            gmail_tools: GmailTools 인스턴스 (프레임워크에서 제공)
            system_prompt: 시스템 프롬프트 (None이면 기본값 사용)
        """
        # 1. LLM 클라이언트 초기화
        # self.client = YourLLMClient(api_key=api_key)
        self.api_key = api_key
        
        # 2. Gmail 도구 저장
        self.gmail = gmail_tools
        
        # 3. 시스템 프롬프트 설정
        if system_prompt is None:
            self.system_prompt = DEFENSE_PROMPTS['none']['prompt']
        else:
            self.system_prompt = system_prompt
        
        # 4. 모델 이름 설정
        self.model = "your-model-name"
    
    def get_tools_schema(self) -> List[Dict]:
        """
        LLM에 전달할 도구 스키마 정의 (OpenAI 스타일 예제)
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_unread_emails",
                    "description": "Get list of unread emails",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of emails",
                                "default": 10
                            }
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_email",
                    "description": "Read a specific email",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {"type": "string"}
                        },
                        "required": ["email_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send an email",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {"type": "string"},
                            "subject": {"type": "string"},
                            "body": {"type": "string"}
                        },
                        "required": ["to", "subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "trash_email",
                    "description": "Move email to trash",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {"type": "string"}
                        },
                        "required": ["email_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "mark_as_read",
                    "description": "Mark email as read",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {"type": "string"}
                        },
                        "required": ["email_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_emails",
                    "description": "Search emails",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "max_results": {"type": "integer", "default": 10}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
    
    def get_provider_name(self) -> str:
        return 'my_agent'
    
    def get_model_name(self) -> str:
        return self.model
    
    async def process_message(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        사용자 메시지 처리 (핵심 구현)
        
        Returns:
            {
                'message': str,           # LLM 최종 응답
                'tools_used': List[str],  # 사용된 도구 목록
                'conversation': List,     # 대화 기록
                'raw_response': Any       # 원본 응답
            }
        """
        if conversation_history is None:
            conversation_history = []
        
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + conversation_history + [
            {"role": "user", "content": user_message}
        ]
        
        tools = self.get_tools_schema()
        tools_used = []
        
        # ============================================================
        # TODO: 여기에 LLM API 호출 및 Tool Use 루프 구현
        # ============================================================
        # 
        # while True:
        #     response = await self.client.chat(
        #         model=self.model,
        #         messages=messages,
        #         tools=tools
        #     )
        #     
        #     if response.has_tool_calls:
        #         for tool_call in response.tool_calls:
        #             result = self._execute_tool(tool_call.name, tool_call.args)
        #             tools_used.append(tool_call.name)
        #             messages.append({"role": "tool", "content": result})
        #     else:
        #         break
        #
        # ============================================================
        
        # Placeholder 응답
        final_response = "Implement your LLM logic here."
        
        # 도구명 정규화 (선택사항)
        if ToolNameMapper:
            tools_used = ToolNameMapper.normalize('my_agent', tools_used)
        
        return {
            'message': final_response,
            'tools_used': tools_used,
            'conversation': messages,
            'raw_response': None
        }
    
    def _execute_tool(self, tool_name: str, tool_input: dict):
        """Gmail 도구 실행"""
        if tool_name == "get_unread_emails":
            return self.gmail.get_unread_emails(max_results=tool_input.get("max_results", 10))
        elif tool_name == "read_email":
            return self.gmail.read_email(tool_input["email_id"])
        elif tool_name == "send_email":
            return self.gmail.send_email(
                to=tool_input["to"],
                subject=tool_input["subject"],
                body=tool_input["body"]
            )
        elif tool_name == "trash_email":
            return self.gmail.trash_email(tool_input["email_id"])
        elif tool_name == "mark_as_read":
            return self.gmail.mark_as_read(tool_input["email_id"])
        elif tool_name == "search_emails":
            return self.gmail.search_emails(
                query=tool_input["query"],
                max_results=tool_input.get("max_results", 10)
            )
        else:
            return {"error": f"Unknown tool: {tool_name}"}