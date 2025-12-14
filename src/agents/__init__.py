"""
Agents 패키지
모든 LLM Agent들을 제공합니다
"""

import os
from typing import Optional, Dict, Any

# 각 Agent 클래스 import (있으면)
try:
    from .claude_agent import ClaudeAgent
except ImportError:
    ClaudeAgent = None

try:
    from .gpt_agent import GPTAgent
except ImportError:
    GPTAgent = None

try:
    from .gemini_agent import GeminiAgent
except ImportError:
    GeminiAgent = None

try:
    from .groq_agent import GroqAgent
except ImportError:
    GroqAgent = None

try:
    from .deepinfra_agent import DeepInfraAgent
except ImportError:
    DeepInfraAgent = None


class AgentFactory:
    """
    LLM Agent Factory
    다양한 LLM을 통한 Agent를 생성합니다
    """
    
    DEFAULT_CONFIGS = {
        'claude': {
            'api_key_env': 'ANTHROPIC_API_KEY',
            'model': 'claude-sonnet-4-5-20250929',
        },
        'gpt': {
            'api_key_env': 'OPENAI_API_KEY',
            'model': 'gpt-4o',
        },
        'gemini': {
            'api_key_env': 'GOOGLE_API_KEY',
            'model': 'gemini-2.0-flash',
        },
        'groq': {
            'api_key_env': 'GROQ_API_KEY',
            'model': 'mixtral-8x7b-32768',
        },
        'deepinfra': {
            'api_key_env': 'DEEPINFRA_API_KEY',
            'model': 'meta-llama/Llama-2-70b-chat-hf',
        },
    }
    
    @staticmethod
    def create_agent(
        agent_name: str,
        gmail_tools,
        system_prompt: str = None,
        configs: Optional[Dict[str, Dict]] = None
    ):
        """Agent 인스턴스 생성"""
        configs = configs or AgentFactory.DEFAULT_CONFIGS
        agent_name = agent_name.lower()
        
        if agent_name not in configs:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        config = configs[agent_name]
        api_key_env = config['api_key_env']
        
        api_key = os.getenv(api_key_env)
        if not api_key:
            raise ValueError(f"Environment variable {api_key_env} not found!")
        
        # 해당 Agent 클래스 반환
        if agent_name == 'claude' and ClaudeAgent:
            return ClaudeAgent(api_key=api_key, gmail_tools=gmail_tools, system_prompt=system_prompt)
        elif agent_name == 'gpt' and GPTAgent:
            return GPTAgent(api_key=api_key, gmail_tools=gmail_tools, system_prompt=system_prompt)
        elif agent_name == 'gemini' and GeminiAgent:
            return GeminiAgent(api_key=api_key, gmail_tools=gmail_tools, system_prompt=system_prompt)
        elif agent_name == 'groq' and GroqAgent:
            return GroqAgent(api_key=api_key, gmail_tools=gmail_tools, system_prompt=system_prompt)
        elif agent_name == 'deepinfra' and DeepInfraAgent:
            return DeepInfraAgent(api_key=api_key, gmail_tools=gmail_tools, system_prompt=system_prompt)
        else:
            raise ValueError(f"Agent {agent_name} not available or not found")


__all__ = ['AgentFactory', 'ClaudeAgent', 'GPTAgent', 'GeminiAgent', 'GroqAgent', 'DeepInfraAgent']
