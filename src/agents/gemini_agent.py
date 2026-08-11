"""
Gemini Agent
Google GenAI SDK (google-genai)와 Gmail Tools 연동 (base.py 상속)

Migration: google-generativeai (deprecated) → google-genai (GA)
"""
import asyncio
from google import genai
from google.genai import types
from typing import List, Dict, Any
import json

from .base import EmailAgent
from .tool_name_mapper import ToolNameMapper
from src.config import DEFENSE_PROMPTS


class GeminiAgent(EmailAgent):
    """Google Gemini API를 통한 이메일 에이전트"""
    
    def __init__(self, api_key: str, gmail_tools, system_prompt: str = None):
        self.client = genai.Client(api_key=api_key)
        self.gmail = gmail_tools
        
        if system_prompt is None:
            self.system_prompt = DEFENSE_PROMPTS['none']['prompt']
        else:
            self.system_prompt = system_prompt
        
        self.model = "gemini-2.5-flash"
    
    def _default_system_prompt(self) -> str:
        return DEFENSE_PROMPTS['none']['prompt']
    
    def _get_tool_declarations(self) -> list:
        """Gmail Tools를 FunctionDeclaration 형식으로 정의"""
        
        return [
            {
                "name": "get_unread_emails",
                "description": "Get list of unread emails",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of emails to retrieve (default: 10)"
                        }
                    }
                }
            },
            {
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
            },
            {
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
                            "description": "CC email address (optional)"
                        },
                        "bcc": {
                            "type": "string",
                            "description": "BCC email address (optional)"
                        }
                    },
                    "required": ["to", "subject", "body"]
                }
            },
            {
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
            },
            {
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
            },
            {
                "name": "search_emails",
                "description": "Search for emails",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results (default: 10)"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]
    
    def get_tools_schema(self) -> List[Dict]:
        return self._get_tool_declarations()
    
    def get_model_name(self) -> str:
        return self.model
    
    def get_agent_name(self) -> str:
        return 'gemini'
    
    async def process_message(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        if conversation_history is None:
            conversation_history = []
        
        tools_used = []
        
        # 도구 설정
        tool_declarations = self._get_tool_declarations()
        tools = [types.Tool(function_declarations=tool_declarations)]
        
        config = types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            tools=tools,
            max_output_tokens=8192,
            temperature=1.0,
        )
        
        # 채팅 세션 생성
        chat = self.client.chats.create(
            model=self.model,
            config=config
        )
        
        # 첫 메시지 전송
        response = await asyncio.to_thread(
            chat.send_message,
            user_message
        )
        self._log_token_usage(response, "gemini")
        
        # Tool call 처리 루프
        max_iterations = 20
        for _ in range(max_iterations):
            has_function_call = False
            
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call:
                        has_function_call = True
                        fc = part.function_call
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        print(f"🔧 Executing tool: {tool_name}")
                        tools_used.append(tool_name)
                        
                        # 도구 실행
                        try:
                            result = self._execute_gmail_tool(tool_name, tool_args)
                        except Exception as e:
                            result = {"success": False, "error": str(e)}
                        
                        # 함수 결과를 모델에 전송
                        function_response = types.Part.from_function_response(
                            name=tool_name,
                            response={"result": json.dumps(result, ensure_ascii=False)}
                        )
                        
                        response = await asyncio.to_thread(
                            chat.send_message,
                            function_response
                        )
                        self._log_token_usage(response, "gemini")
                        break  # 한 번에 하나씩 처리
            
            if not has_function_call:
                break
        
        # 최종 텍스트 응답 추출
        text_content = ""
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.text:
                    text_content += part.text
        
        # 도구명 정규화
        tools_used = ToolNameMapper.normalize('gemini', tools_used)
        
        return {
            'message': text_content,
            'tools_used': tools_used,
            'conversation': conversation_history + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": text_content}
            ],
            'raw_response': response
        }
    
    def _execute_gmail_tool(self, tool_name: str, tool_input: dict):
        """Gmail Tools 실행"""
        
        if tool_name == "get_unread_emails":
            max_results = tool_input.get("max_results", 10)
            emails = self.gmail.get_unread_emails(max_results=max_results)
            for email in emails:
                if email.get('body') and len(email['body']) > 300:
                    email['body'] = email['body'][:300] + "...(truncated)"
            return emails
        
        elif tool_name == "read_email":
            email = self.gmail.read_email(tool_input["email_id"])
            if email and isinstance(email, dict) and email.get('body') and len(email['body']) > 300:
                email['body'] = email['body'][:300] + "...(truncated)"
            return email
        
        elif tool_name == "send_email":
            return self._send_email_with_log(tool_input)
        elif tool_name == "trash_email":
            return self.gmail.trash_email(tool_input["email_id"])
        
        elif tool_name == "mark_as_read":
            return self.gmail.mark_as_read(tool_input["email_id"])
        
        elif tool_name == "search_emails":
            max_results = tool_input.get("max_results", 10)
            emails = self.gmail.search_emails(
                query=tool_input["query"],
                max_results=max_results
            )
            for email in emails:
                if email.get('body') and len(email['body']) > 300:
                    email['body'] = email['body'][:300] + "...(truncated)"
            return emails
        
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}