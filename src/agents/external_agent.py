"""
External Agent - 외부 API 서버와 통신

사용자가 자체 Agent 서버를 구현하고 URL만 제공하면 됨.
이를 통해 어떤 언어/프레임워크로든 Agent를 구현하고 평가받을 수 있음.

API 스펙:
    POST /process
    Request:
        {
            "message": "읽지 않은 메일 처리해줘",
            "conversation_history": []
        }
    Response:
        {
            "message": "메일을 처리했습니다",
            "tools_used": ["get_unread_emails", "send_email"]
        }

사용 예:
    # 사용자가 자기 Agent 서버 실행
    python my_agent_server.py --port 8000
    
    # 우리 프레임워크에서 테스트
    python main.py --mode benchmark --agent external --api-url http://localhost:8000
"""

import httpx
from typing import List, Dict, Any, Optional
from .base import EmailAgent


class ExternalAgent(EmailAgent):
    """외부 사용자 Agent API 호출"""
    
    def __init__(self, api_url: str, gmail_tools=None, system_prompt: str = None, timeout: int = 120):
        """
        Args:
            api_url: 사용자 Agent 서버 URL (예: "http://localhost:8000")
            gmail_tools: 평가용으로만 사용 (Agent 서버가 자체 Gmail 관리)
            system_prompt: 사용 안 함 (Agent 서버가 자체 관리)
            timeout: API 타임아웃 (초), 기본 120초
        """
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout
        self.gmail = gmail_tools  # 평가용으로만 사용
    
    def get_tools_schema(self) -> List[Dict]:
        """외부 Agent가 자체 관리하므로 빈 리스트 반환"""
        return []
    
    def get_model_name(self) -> str:
        return "external"
    
    def get_agent_name(self) -> str:
        return "external"
    
    async def process_message(
        self, 
        user_message: str, 
        conversation_history: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        외부 Agent API 호출
        
        사용자 API 스펙:
            POST /process
            Request:  {"message": str, "conversation_history": list}
            Response: {"message": str, "tools_used": list}
        
        Args:
            user_message: 사용자 메시지
            conversation_history: 대화 기록 (optional)
        
        Returns:
            {
                'message': str,       # Agent 응답
                'tools_used': list,   # 사용한 도구 목록
                'conversation': list, # 업데이트된 대화 기록
                'raw_response': dict  # 원본 응답
            }
        """
        if conversation_history is None:
            conversation_history = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/process",
                    json={
                        "message": user_message,
                        "conversation_history": conversation_history
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                return {
                    'message': data.get('message', ''),
                    'tools_used': data.get('tools_used', []),
                    'conversation': conversation_history + [
                        {"role": "user", "content": user_message},
                        {"role": "assistant", "content": data.get('message', '')}
                    ],
                    'raw_response': data
                }
        
        except httpx.TimeoutException:
            return {
                'message': f"Error: API timeout ({self.timeout}s)",
                'tools_used': [],
                'conversation': conversation_history,
                'error': 'timeout'
            }
        
        except httpx.HTTPStatusError as e:
            return {
                'message': f"Error: HTTP {e.response.status_code}",
                'tools_used': [],
                'conversation': conversation_history,
                'error': str(e)
            }
        
        except httpx.ConnectError:
            return {
                'message': f"Error: Cannot connect to {self.api_url}. Is the server running?",
                'tools_used': [],
                'conversation': conversation_history,
                'error': 'connection_error'
            }
        
        except Exception as e:
            return {
                'message': f"Error: {str(e)}",
                'tools_used': [],
                'conversation': conversation_history,
                'error': str(e)
            }
    
    async def health_check(self) -> bool:
        """
        서버 상태 확인
        
        GET /health 엔드포인트 호출
        
        Returns:
            bool: 서버가 응답하면 True
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.api_url}/health")
                return response.status_code == 200
        except:
            return False
    
    async def get_server_info(self) -> Dict[str, Any]:
        """
        서버 정보 조회 (optional)
        
        GET /info 엔드포인트 호출
        
        Returns:
            dict: 서버 정보 (name, version, model 등)
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.api_url}/info")
                if response.status_code == 200:
                    return response.json()
                return {}
        except:
            return {}