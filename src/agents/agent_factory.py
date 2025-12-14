"""
AgentFactory - Agent를 동적으로 생성하는 팩토리 패턴

이 팩토리는 명령행 인자나 환경변수에 따라 
다양한 LLM API의 Agent를 런타임에 생성합니다.

사용 예:
    from src.agents.agent_factory import AgentFactory
    
    agent = AgentFactory.create_agent(
        agent_name='gpt',
        gmail_tools=gmail_tools,
        system_prompt=system_prompt
    )
    
    # External Agent (사용자 API 서버)
    agent = AgentFactory.create_agent(
        agent_name='external',
        gmail_tools=gmail_tools,
        api_url='http://localhost:8000'
    )
"""

import os
from typing import Optional, Type


class AgentFactory:
    """
    Agent 생성 팩토리
    
    각 LLM API에 대응하는 Agent 클래스를 동적으로 생성하고 인스턴스화합니다.
    """
    
    # 등록된 Agent 클래스들
    _AGENTS: dict = {}
    
    @staticmethod
    def register_agent(agent_name: str, agent_class) -> None:
        """
        새로운 Agent 클래스 등록
        
        Args:
            agent_name (str): Agent 이름 ("claude", "gpt", "gemini", "groq", "deepinfra", "external")
            agent_class: EmailAgent를 상속받은 클래스
        
        Example:
            >>> from src.agents.gpt_agent import GPTAgent
            >>> AgentFactory.register_agent('gpt', GPTAgent)
        """
        AgentFactory._AGENTS[agent_name.lower()] = agent_class
    
    @staticmethod
    def create_agent(
        agent_name: str,
        gmail_tools,
        system_prompt: Optional[str] = None,
        **kwargs
    ):
        """
        동적으로 Agent를 생성
        
        Args:
            agent_name (str): 생성할 Agent 이름 ("claude", "gpt", "gemini", "groq", "deepinfra", "external")
            gmail_tools: GmailTools 인스턴스
            system_prompt (Optional[str]): 커스텀 시스템 프롬프트 (기본값: None)
            **kwargs: 추가 파라미터
                - api_url (str): External Agent용 API URL (기본값: "http://localhost:8000")
        
        Returns:
            EmailAgent: 생성된 Agent 인스턴스
        
        Raises:
            ValueError: 알 수 없는 agent_name이거나 필수 API 키가 없는 경우
        
        Example:
            >>> agent = AgentFactory.create_agent(
            ...     agent_name='claude',
            ...     gmail_tools=gmail_tools,
            ...     system_prompt="당신은 이메일 비서입니다."
            ... )
            
            >>> # External Agent
            >>> agent = AgentFactory.create_agent(
            ...     agent_name='external',
            ...     gmail_tools=gmail_tools,
            ...     api_url='http://localhost:8000'
            ... )
        """
        agent_name_lower = agent_name.lower()
        
        # External Agent 특별 처리 (API 키 불필요)
        if agent_name_lower == 'external':
            from .external_agent import ExternalAgent
            api_url = kwargs.get('api_url', 'http://localhost:8000')
            return ExternalAgent(api_url=api_url, gmail_tools=gmail_tools)
        
        # 1. 등록된 Agent 클래스 확인
        if agent_name_lower in AgentFactory._AGENTS:
            agent_class = AgentFactory._AGENTS[agent_name_lower]
            api_key = AgentFactory._get_api_key(agent_name_lower)
            return agent_class(api_key, gmail_tools, system_prompt)
        
        # 2. 등록되지 않았으면 동적 import 시도
        try:
            agent_class = AgentFactory._import_agent_class(agent_name_lower)
            api_key = AgentFactory._get_api_key(agent_name_lower)
            return agent_class(api_key, gmail_tools, system_prompt)
        except (ImportError, AttributeError) as e:
            raise ValueError(
                f"Agent '{agent_name}' not available or not found. "
                f"Supported agents: {AgentFactory._get_supported_agents()}"
            ) from e
    
    @staticmethod
    def _import_agent_class(agent_name: str):
        """
        Agent 클래스를 동적으로 import
        
        Args:
            agent_name (str): Agent 이름 (소문자)
        
        Returns:
            Type[EmailAgent]: import된 클래스
        
        Raises:
            ImportError: 모듈을 찾을 수 없는 경우
            AttributeError: 클래스를 찾을 수 없는 경우
        """
        # 모듈명: claude_agent, gpt_agent, gemini_agent, groq_agent, deepinfra_agent, external_agent
        module_name = f"{agent_name}_agent"
        
        try:
            module = __import__(f"src.agents.{module_name}", fromlist=[module_name])
        except ImportError:
            try:
                module = __import__(f"agents.{module_name}", fromlist=[module_name])
            except ImportError:
                raise ImportError(f"Cannot import agents.{module_name}")
        
        # 클래스명: ClaudeAgent, GPTAgent, GeminiAgent, GroqAgent, DeepInfraAgent, ExternalAgent
        class_name = AgentFactory._get_class_name(agent_name)
        
        if not hasattr(module, class_name):
            raise AttributeError(f"Class '{class_name}' not found in agents.{module_name}")
        
        return getattr(module, class_name)
    
    @staticmethod
    def _get_class_name(agent_name: str) -> str:
        """
        Agent 이름을 클래스명으로 변환
        
        Args:
            agent_name (str): Agent 이름 (소문자)
        
        Returns:
            str: 클래스명
        
        Example:
            >>> AgentFactory._get_class_name('claude')
            'ClaudeAgent'
            >>> AgentFactory._get_class_name('gpt')
            'GPTAgent'
        """
        name_mapping = {
            'claude': 'ClaudeAgent',
            'gpt': 'GPTAgent',
            'gemini': 'GeminiAgent',
            'groq': 'GroqAgent',
            'deepinfra': 'DeepInfraAgent',
            'external': 'ExternalAgent',
        }
        
        return name_mapping.get(agent_name, f"{agent_name.capitalize()}Agent")
    
    @staticmethod
    def _get_api_key(agent_name: str) -> str:
        """
        Agent에 필요한 API 키를 환경변수에서 가져오기
        
        Args:
            agent_name (str): Agent 이름 (소문자)
        
        Returns:
            str: API 키
        
        Raises:
            ValueError: API 키를 찾을 수 없는 경우
        """
        api_key_mapping = {
            'claude': 'ANTHROPIC_API_KEY',
            'gpt': 'OPENAI_API_KEY',
            'gemini': 'GEMINI_API_KEY',
            'groq': 'GROQ_API_KEY',
            'deepinfra': 'DEEPINFRA_API_KEY',
            'external': None,  # API 키 불필요
        }
        
        env_var = api_key_mapping.get(agent_name)
        
        # external은 API 키 불필요
        if env_var is None:
            return ""
        
        # 알 수 없는 agent
        if agent_name not in api_key_mapping:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        api_key = os.environ.get(env_var)
        if not api_key:
            raise ValueError(
                f"{env_var} environment variable not set. "
                f"Please set it before using {agent_name} agent."
            )
        
        return api_key
    
    @staticmethod
    def _get_supported_agents() -> list:
        """
        지원하는 Agent 목록 반환
        
        Returns:
            list: 지원하는 Agent 이름 목록
        """
        return ['claude', 'gpt', 'gemini', 'groq', 'deepinfra', 'external']
    
    @staticmethod
    def get_available_agents() -> dict:
        """
        사용 가능한 Agent 목록 반환 (등록된 + 구현된)
        
        Returns:
            dict: {'agent_name': 'AgentClass'} 형식
        """
        available = {}
        
        for agent_name in AgentFactory._get_supported_agents():
            try:
                if agent_name == 'external':
                    available[agent_name] = 'ExternalAgent'
                else:
                    agent_class = AgentFactory._import_agent_class(agent_name)
                    available[agent_name] = agent_class.__name__
            except (ImportError, AttributeError):
                # 아직 구현되지 않은 Agent는 스킵
                pass
        
        return available
    
    @staticmethod
    def is_agent_available(agent_name: str) -> bool:
        """
        특정 Agent가 사용 가능한지 확인
        
        Args:
            agent_name (str): Agent 이름
        
        Returns:
            bool: 사용 가능 여부
        """
        try:
            if agent_name.lower() == 'external':
                return True
            AgentFactory._import_agent_class(agent_name.lower())
            AgentFactory._get_api_key(agent_name.lower())
            return True
        except (ImportError, AttributeError, ValueError):
            return False