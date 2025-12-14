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