"""
Llama 3.3 70B Agent
Meta Llama 3.3 70B (Together AI 경유)와 Gmail Tools 연동 (base.py 상속)

GPTAgent와의 차이점:
1. base_url: "https://api.together.xyz/v1" (Together AI)
2. model: "meta-llama/Llama-3.3-70B-Instruct-Turbo"
3. api_key: OPENAI_API_KEY → TOGETHER_API_KEY
4. 도구 호출 에러 핸들링 강화:
   - tool_calls가 None/비어있는 경우 대비
   - function.arguments JSON 파싱 실패 대비
   (Llama의 도구 호출 포맷이 불안정할 수 있음 — vLLM 공식 문서 경고 참고)
"""
import asyncio
from openai import AsyncOpenAI
from typing import List, Dict, Any
import json

from .base import EmailAgent
from .tool_name_mapper import ToolNameMapper
from src.config import DEFENSE_PROMPTS


class LlamaAgent(EmailAgent):
    """Llama  3.3 70B를 통한 이메일 에이전트 (Together AI 경유, OpenAI SDK 호환)"""
        
    def __init__(self, api_key: str, gmail_tools, system_prompt: str = None):
        """
        Llama 3.3 70B Agent 초기화
        
        Args:
            api_key: Together AI API 키
            gmail_tools: GmailTools 인스턴스
            system_prompt: 시스템 프롬프트 (없으면 방어 없음 사용)
        """
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.together.xyz/v1"  # ✅ Together AI 엔드포인트
        )
        self.gmail = gmail_tools
        if system_prompt is None:
            self.system_prompt = DEFENSE_PROMPTS['none']['prompt']
        else:
            self.system_prompt = system_prompt
        self.model = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    
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
        return 'llama'
    
    async def process_message(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """
        사용자 메시지 처리
        
        GPTAgent와의 차이점:
        - tool_calls가 None/비어있는 경우에 대한 방어적 처리 추가
        - function.arguments JSON 파싱 실패 시 에러 핸들링 추가
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
                tools=tools,
                tool_choice="auto"
            )
            self._log_token_usage(response, "openai")
            
            finish_reason = response.choices[0].finish_reason
            assistant_message = response.choices[0].message
            
            if finish_reason == "stop":
                text_content = assistant_message.content or ""
                tools_used = ToolNameMapper.normalize('llama', tools_used)
                
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
                # ⚠️ Llama 3.3 70B: tool_calls가 None이거나 비어있을 수 있음
                if not assistant_message.tool_calls:
                    text_content = assistant_message.content or "(No tool calls generated)"
                    tools_used = ToolNameMapper.normalize('llama', tools_used)
                    return {
                        'message': text_content,
                        'tools_used': tools_used,
                        'conversation': messages,
                        'raw_response': response
                    }
                
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
                    
                    # ⚠️ Llama 3.3 70B: arguments가 유효한 JSON이 아닐 수 있음
                    try:
                        tool_input = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        print(f"⚠️ JSON parse failed for tool {tool_name}: {tool_call.function.arguments}")
                        tools_used.append(tool_name)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps({
                                "success": False, 
                                "error": "Invalid arguments format from model"
                            })
                        })
                        continue
                    
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
            
        # 모든 에이전트의 _execute_gmail_tool 메서드에서 send_email 분기를 아래로 교체
        # (llama_agent.py, gpt_agent.py, deepseek_agent.py, o4mini_agent.py 등 모두 동일)

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
