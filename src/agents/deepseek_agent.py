"""
DeepSeek Agent
DeepSeek V3.2 API와 Gmail Tools 연동 (base.py 상속)

GPTAgent와의 차이점:
1. base_url: "https://api.deepseek.com" 추가
2. model: "gpt-4o" → "deepseek-chat" (자동으로 최신 V3.2 적용)
3. api_key: OPENAI_API_KEY → DEEPSEEK_API_KEY

나머지 도구 정의, 호출 루프, _execute_gmail_tool()은 GPTAgent와 100% 동일.
DeepSeek API는 OpenAI SDK와 완전 호환 (finish_reason, tool_calls 형식 동일).
"""
import asyncio
from openai import AsyncOpenAI
from typing import List, Dict, Any
import json

from .base import EmailAgent
from .tool_name_mapper import ToolNameMapper
from src.config import DEFENSE_PROMPTS


class DeepSeekAgent(EmailAgent):
    """DeepSeek V3.2를 통한 이메일 에이전트 (OpenAI SDK 호환)"""
        
    def __init__(self, api_key: str, gmail_tools, system_prompt: str = None):
        """
        DeepSeek Agent 초기화
        
        Args:
            api_key: DeepSeek API 키
            gmail_tools: GmailTools 인스턴스
            system_prompt: 시스템 프롬프트 (없으면 방어 없음 사용)
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"  # ✅ DeepSeek API 엔드포인트
        )
        self.gmail = gmail_tools
        if system_prompt is None:
            self.system_prompt = DEFENSE_PROMPTS['none']['prompt']
        else:
            self.system_prompt = system_prompt
        self.model = "deepseek-chat"  # ✅ 자동으로 최신 V3.2 적용
    
    def _default_system_prompt(self) -> str:
        """기본 시스템 프롬프트 (방어 없음)"""
        return DEFENSE_PROMPTS['none']['prompt']

    def _get_gmail_tools_for_gpt(self) -> List[Dict]:
        """Gmail Tools를 OpenAI function format으로 변환 (GPTAgent와 동일)"""
        
        tools = [
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
                                "description": "Maximum number of emails to retrieve (default: 10)",
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
                    "description": "Read the content of a specific email",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "email_id": {
                                "type": "string",
                                "description": "The ID of the email to read"
                            }
                        },
                        "required": ["email_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Send a new email",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body"
                            },
                            "cc": {
                                "type": "string",
                                "description": "CC (optional)"
                            },
                            "bcc": {
                                "type": "string",
                                "description": "BCC (optional)"
                            }
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
                            "email_id": {
                                "type": "string",
                                "description": "The ID of the email to trash"
                            }
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
                            "email_id": {
                                "type": "string",
                                "description": "The ID of the email to mark as read"
                            }
                        },
                        "required": ["email_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_emails",
                    "description": "Search for emails",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Gmail search query (e.g., 'from:example@gmail.com', 'subject:important')"
                            },
                            "max_results": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        
        return tools
    
    def get_tools_schema(self) -> List[Dict]:
        """base.py의 추상 메서드 구현"""
        return self._get_gmail_tools_for_gpt()
    
    def get_model_name(self) -> str:
        """base.py의 추상 메서드 구현"""
        return self.model
    
    def get_agent_name(self) -> str:
        """base.py의 추상 메서드 구현"""
        return 'deepseek'
    
    async def process_message(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        사용자 메시지 처리 (GPTAgent와 동일한 로직)
        """
        if conversation_history is None:
            conversation_history = []
        
        messages = [
            {"role": "system", "content": self.system_prompt}
        ] + conversation_history + [
            {"role": "user", "content": user_message}
        ]
        
        tools = self._get_gmail_tools_for_gpt()
        tools_used = []
        
        while True:
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=8192,
                temperature=1.0,
                messages=messages,
                tools=tools
            )
            self._log_token_usage(response, "openai")
            
            finish_reason = response.choices[0].finish_reason
            assistant_message = response.choices[0].message
            
            if finish_reason == "stop":
                text_content = assistant_message.content or ""
                tools_used = ToolNameMapper.normalize('deepseek', tools_used)
                
                return {
                    'message': text_content,
                    'tools_used': tools_used,
                    'conversation': messages + [
                        {
                            "role": "assistant",
                            "content": assistant_message.content
                        }
                    ],
                    'raw_response': response
                }
            
            elif finish_reason == "tool_calls":
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments
                            }
                        }
                        for tool_call in assistant_message.tool_calls
                    ]
                })
                
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)
                    
                    print(f"🔧 Executing tool: {tool_name}")
                    tools_used.append(tool_name)
                    
                    try:
                        result = self._execute_gmail_tool(tool_name, tool_input)
                        content = json.dumps(result, ensure_ascii=False)
                    except Exception as e:
                        content = json.dumps({"success": False, "error": str(e)})
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": content
                    })
            
            else:
                return {
                    'message': f"Unexpected finish reason: {finish_reason}",
                    'tools_used': tools_used,
                    'conversation': messages,
                    'raw_response': response
                }
    
    def _execute_gmail_tool(self, tool_name: str, tool_input: dict):
        """Gmail Tools 실행 (GPTAgent와 동일)"""
        
        if tool_name == "get_unread_emails":
            max_results = tool_input.get("max_results", 10)
            return self.gmail.get_unread_emails(max_results=max_results)
        
        elif tool_name == "read_email":
            return self.gmail.read_email(tool_input["email_id"])
        
        elif tool_name == "send_email":
            return self._send_email_with_log(tool_input)
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
