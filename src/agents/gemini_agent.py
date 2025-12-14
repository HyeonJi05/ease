"""
Gemini Agent
Google Gemini API와 Gmail Tools 연동 (base.py 상속)
"""
import asyncio
import google.generativeai as genai
from typing import List, Dict, Any
import json

from .base import EmailAgent
from .tool_name_mapper import ToolNameMapper
from src.config import DEFENSE_PROMPTS


class GeminiAgent(EmailAgent):
    """Google Gemini API를 통한 이메일 에이전트"""
    
    def __init__(self, api_key: str, gmail_tools, system_prompt: str = None):
        genai.configure(api_key=api_key)
        self.gmail = gmail_tools
        
        if system_prompt is None:
            self.system_prompt = DEFENSE_PROMPTS['none']['prompt']
        else:
            self.system_prompt = system_prompt
        
        self.model = "gemini-2.0-flash"
    
    def _default_system_prompt(self) -> str:
        return DEFENSE_PROMPTS['none']['prompt']
    
    def _get_gmail_tools_for_gemini(self):
        """Gmail Tools를 Gemini function declaration 형식으로 변환"""
        
        # Gemini용 함수 선언
        def get_unread_emails(max_results: int = 10) -> dict:
            """Get list of unread emails"""
            pass
        
        def read_email(email_id: str) -> dict:
            """Read the content of a specific email"""
            pass
        
        def send_email(to: str, subject: str, body: str, cc: str = None, bcc: str = None) -> dict:
            """Send a new email"""
            pass
        
        def trash_email(email_id: str) -> dict:
            """Move email to trash"""
            pass
        
        def mark_as_read(email_id: str) -> dict:
            """Mark email as read"""
            pass
        
        def search_emails(query: str, max_results: int = 10) -> dict:
            """Search for emails"""
            pass
        
        return [get_unread_emails, read_email, send_email, trash_email, mark_as_read, search_emails]
    
    def get_tools_schema(self) -> List[Dict]:
        return []  # Gemini uses function references
    
    def get_model_name(self) -> str:
        return self.model
    
    def get_agent_name(self) -> str:
        return 'gemini'
    
    async def process_message(self, user_message: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        if conversation_history is None:
            conversation_history = []
        
        tools_used = []
        
        # Gemini 모델 생성 (with tools)
        model = genai.GenerativeModel(
            self.model,
            system_instruction=self.system_prompt,
            tools=self._get_gmail_tools_for_gemini()
        )
        
        # 채팅 시작
        chat = model.start_chat(history=[])
        
        # 첫 메시지 전송
        response = await asyncio.to_thread(
            chat.send_message,
            user_message
        )
        
        # Tool call 처리 루프
        while response.candidates[0].content.parts:
            has_function_call = False
            
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'function_call') and part.function_call:
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
                    
                    # 결과 전송
                    response = await asyncio.to_thread(
                        chat.send_message,
                        genai.protos.Content(
                            parts=[genai.protos.Part(
                                function_response=genai.protos.FunctionResponse(
                                    name=tool_name,
                                    response={"result": json.dumps(result, ensure_ascii=False)}
                                )
                            )]
                        )
                    )
                    break  # 한 번에 하나씩 처리
            
            if not has_function_call:
                break
        
        # 최종 텍스트 응답 추출
        text_content = ""
        for part in response.candidates[0].content.parts:
            if hasattr(part, 'text') and part.text:
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
            # body 크기 제한
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