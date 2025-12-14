"""
Claude Agent
Claude API와 Gmail Tools 연동 (base.py 상속)
"""
import anthropic
from typing import List, Dict, Any
import json

# ✅ 추가: base.py와 tool_name_mapper.py import
from .base import EmailAgent
from .tool_name_mapper import ToolNameMapper
from src.config import DEFENSE_PROMPTS


class ClaudeAgent(EmailAgent):  # ✅ 변경: base.EmailAgent 상속
    """Claude API를 통한 이메일 에이전트"""
    
    def __init__(self, api_key: str, gmail_tools, system_prompt: str = None):
        """
        Claude Agent 초기화
        
        Args:
            api_key: Anthropic API 키
            gmail_tools: GmailTools 인스턴스
            system_prompt: 시스템 프롬프트 (없으면 방어 없음 사용)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.gmail = gmail_tools
        # ✅ system_prompt이 None이면 config에서 기본값 가져오기
        if system_prompt is None:
            self.system_prompt = DEFENSE_PROMPTS['none']['prompt']
        else:
            self.system_prompt = system_prompt
        self.model = "claude-sonnet-4-5-20250929"
        
    def _default_system_prompt(self) -> str:
        """기본 시스템 프롬프트 (config에서 가져오기)"""
        return DEFENSE_PROMPTS['none']['prompt']
    
    def _get_gmail_tools_for_claude(self) -> List[Dict]:
        """Gmail Tools를 Claude API 형식으로 변환"""
        
        tools = [
            {
                "name": "get_unread_emails",
                "description": "읽지 않은 메일 목록을 가져옵니다",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "가져올 최대 메일 개수 (기본값: 10)",
                            "default": 10
                        }
                    }
                }
            },
            {
                "name": "read_email",
                "description": "특정 메일의 상세 내용을 읽습니다",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "email_id": {
                            "type": "string",
                            "description": "읽을 메일의 ID"
                        }
                    },
                    "required": ["email_id"]
                }
            },
            {
                "name": "send_email",
                "description": "새 메일을 전송합니다",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "to": {
                            "type": "string",
                            "description": "받는 사람 이메일 주소"
                        },
                        "subject": {
                            "type": "string",
                            "description": "메일 제목"
                        },
                        "body": {
                            "type": "string",
                            "description": "메일 본문"
                        },
                        "cc": {
                            "type": "string",
                            "description": "참조 (선택)"
                        },
                        "bcc": {
                            "type": "string",
                            "description": "숨은 참조 (선택)"
                        }
                    },
                    "required": ["to", "subject", "body"]
                }
            },
            {
                "name": "trash_email",
                "description": "메일을 휴지통으로 이동합니다",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "email_id": {
                            "type": "string",
                            "description": "휴지통으로 이동할 메일의 ID"
                        }
                    },
                    "required": ["email_id"]
                }
            },
            {
                "name": "mark_as_read",
                "description": "메일을 읽음으로 표시합니다",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "email_id": {
                            "type": "string",
                            "description": "읽음으로 표시할 메일의 ID"
                        }
                    },
                    "required": ["email_id"]
                }
            },
            {
                "name": "search_emails",
                "description": "특정 조건으로 메일을 검색합니다",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Gmail 검색 쿼리 (예: 'from:example@gmail.com', 'subject:important')"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "최대 결과 개수 (기본값: 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
        
        return tools
    
    def get_tools_schema(self) -> List[Dict]:
        """base.py의 추상 메서드 구현"""
        return self._get_gmail_tools_for_claude()
    
    def get_model_name(self) -> str:
        """base.py의 추상 메서드 구현"""
        return self.model
    
    def get_agent_name(self) -> str:
        """base.py의 추상 메서드 구현"""
        return 'claude'
    
    async def process_message(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        사용자 메시지 처리 (base.py의 추상 메서드 구현)
        
        Args:
            user_message: 사용자 입력
            conversation_history: 이전 대화 기록
        
        Returns:
            {'message': str, 'tools_used': List[str], 'conversation': List[Dict], 'raw_response': Any}
        """
        if conversation_history is None:
            conversation_history = []
        
        messages = conversation_history + [
            {"role": "user", "content": user_message}
        ]
        
        tools = self._get_gmail_tools_for_claude()
        tools_used = []
        
        # Claude API 호출 루프
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=self.system_prompt,
                messages=messages,
                tools=tools
            )
            
            if response.stop_reason == "end_turn":
                # 최종 응답
                text_content = ""
                for content in response.content:
                    if content.type == "text":
                        text_content += content.text
                
                # ✅ 추가: 도구명 정규화 (1줄!)
                tools_used = ToolNameMapper.normalize('claude', tools_used)
                
                return {
                    'message': text_content,
                    'tools_used': tools_used,
                    'conversation': messages + [
                        {"role": "assistant", "content": response.content}
                    ],
                    'raw_response': response  # ✅ 추가: raw_response 반환
                }
            
            elif response.stop_reason == "tool_use":
                # 도구 실행
                assistant_message = response.content
                messages.append({"role": "assistant", "content": assistant_message})
                
                tool_results = []
                for content in assistant_message:
                    if content.type == "tool_use":
                        tool_name = content.name
                        tool_input = content.input
                        
                        print(f"🔧 Executing tool: {tool_name}")
                        tools_used.append(tool_name)
                        
                        try:
                            # Gmail Tools 실행
                            result = self._execute_gmail_tool(tool_name, tool_input)
                            
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": json.dumps(result, ensure_ascii=False)
                            })
                        except Exception as e:
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": content.id,
                                "content": json.dumps({"success": False, "error": str(e)}),
                                "is_error": True
                            })
                
                messages.append({"role": "user", "content": tool_results})
            
            else:
                return {
                    'message': f"Unexpected stop reason: {response.stop_reason}",
                    'tools_used': tools_used,
                    'conversation': messages,
                    'raw_response': response
                }
    
    def _execute_gmail_tool(self, tool_name: str, tool_input: dict):
        """Gmail Tools 실행"""
        
        if tool_name == "get_unread_emails":
            max_results = tool_input.get("max_results", 10)
            return self.gmail.get_unread_emails(max_results=max_results)
        
        elif tool_name == "read_email":
            return self.gmail.read_email(tool_input["email_id"])
        
        elif tool_name == "send_email":
            return self.gmail.send_email(
                to=tool_input["to"],
                subject=tool_input["subject"],
                body=tool_input["body"],
                cc=tool_input.get("cc"),
                bcc=tool_input.get("bcc")
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
            return {"success": False, "error": f"Unknown tool: {tool_name}"}