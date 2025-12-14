"""
ToolNameMapper - API별 도구명을 표준 형식으로 정규화

각 LLM API는 도구명 형식이 다릅니다:
- Claude: snake_case (read_email, send_email, ...)
- GPT-4o: snake_case (read_email, send_email, ...)
- Gemini: camelCase (readEmail, sendEmail, ...)
- Groq: snake_case (read_email, send_email, ...)
- DeepInfra: snake_case (read_email, send_email, ...)

이 클래스는 모든 API의 도구명을 표준 형식(snake_case)으로 변환합니다.
"""

from typing import List, Dict


class ToolNameMapper:
    """API별 도구명을 표준 형식으로 정규화"""
    
    # API별 도구명 매핑 (원본 형식 → 표준 형식)
    MAPPINGS = {
        'claude': {
            'get_unread_emails': 'get_unread_emails',
            'read_email': 'read_email',
            'send_email': 'send_email',
            'trash_email': 'trash_email',
            'mark_as_read': 'mark_as_read',
            'mark_as_unread': 'mark_as_unread',
            'search_emails': 'search_emails',
            'delete_email_permanently': 'delete_email_permanently',
            'get_labels': 'get_labels',
            'add_label': 'add_label',
        },
        'gpt': {
            'get_unread_emails': 'get_unread_emails',
            'read_email': 'read_email',
            'send_email': 'send_email',
            'trash_email': 'trash_email',
            'mark_as_read': 'mark_as_read',
            'mark_as_unread': 'mark_as_unread',
            'search_emails': 'search_emails',
            'delete_email_permanently': 'delete_email_permanently',
            'get_labels': 'get_labels',
            'add_label': 'add_label',
        },
        'gemini': {
            # Gemini는 camelCase를 사용하므로 변환 필요
            'getUnreadEmails': 'get_unread_emails',
            'readEmail': 'read_email',
            'sendEmail': 'send_email',
            'trashEmail': 'trash_email',
            'markAsRead': 'mark_as_read',
            'markAsUnread': 'mark_as_unread',
            'searchEmails': 'search_emails',
            'deleteEmailPermanently': 'delete_email_permanently',
            'getLabels': 'get_labels',
            'addLabel': 'add_label',
        },
        'groq': {
            'get_unread_emails': 'get_unread_emails',
            'read_email': 'read_email',
            'send_email': 'send_email',
            'trash_email': 'trash_email',
            'mark_as_read': 'mark_as_read',
            'mark_as_unread': 'mark_as_unread',
            'search_emails': 'search_emails',
            'delete_email_permanently': 'delete_email_permanently',
            'get_labels': 'get_labels',
            'add_label': 'add_label',
        },
        'deepinfra': {
            'get_unread_emails': 'get_unread_emails',
            'read_email': 'read_email',
            'send_email': 'send_email',
            'trash_email': 'trash_email',
            'mark_as_read': 'mark_as_read',
            'mark_as_unread': 'mark_as_unread',
            'search_emails': 'search_emails',
            'delete_email_permanently': 'delete_email_permanently',
            'get_labels': 'get_labels',
            'add_label': 'add_label',
        },
    }
    
    @staticmethod
    def normalize(agent_name: str, tools: List[str]) -> List[str]:
        """
        도구명을 표준 형식으로 정규화
        
        Args:
            agent_name (str): Agent 이름 ("claude", "gpt", "gemini", "groq", "deepinfra")
            tools (List[str]): 원본 도구명 리스트
        
        Returns:
            List[str]: 정규화된 도구명 리스트 (중복 제거)
        
        Raises:
            ValueError: 알 수 없는 agent_name인 경우
        
        Example:
            >>> ToolNameMapper.normalize('gemini', ['readEmail', 'sendEmail'])
            ['read_email', 'send_email']
        """
        agent_name_lower = agent_name.lower()
        
        if agent_name_lower not in ToolNameMapper.MAPPINGS:
            raise ValueError(
                f"Unknown agent: {agent_name}. "
                f"Supported agents: {list(ToolNameMapper.MAPPINGS.keys())}"
            )
        
        mapping = ToolNameMapper.MAPPINGS[agent_name_lower]
        normalized_tools = []
        
        for tool in tools:
            if tool in mapping:
                normalized_tool = mapping[tool]
                # 중복 제거
                if normalized_tool not in normalized_tools:
                    normalized_tools.append(normalized_tool)
            else:
                # 매핑되지 않은 도구는 그대로 유지
                if tool not in normalized_tools:
                    normalized_tools.append(tool)
        
        return normalized_tools
    
    @staticmethod
    def get_standard_tools() -> List[str]:
        """
        표준 도구명 목록 반환 (모든 도구명이 통일된 형식)
        
        Returns:
            List[str]: 표준화된 도구명 목록
        """
        # Claude의 매핑이 표준이므로 그것을 기준으로 사용
        return list(ToolNameMapper.MAPPINGS['claude'].values())
    
    @staticmethod
    def add_agent_mapping(
        agent_name: str, 
        mapping: Dict[str, str]
    ) -> None:
        """
        새로운 Agent의 도구명 매핑 추가 (확장성)
        
        Args:
            agent_name (str): 새 Agent 이름
            mapping (Dict[str, str]): 원본 도구명 → 표준 도구명 매핑
        
        Example:
            >>> new_mapping = {
            ...     'readEmail': 'read_email',
            ...     'sendEmail': 'send_email',
            ... }
            >>> ToolNameMapper.add_agent_mapping('custom_agent', new_mapping)
        """
        ToolNameMapper.MAPPINGS[agent_name.lower()] = mapping
    
    @staticmethod
    def get_reverse_mapping(agent_name: str) -> Dict[str, str]:
        """
        표준 도구명 → 원본 도구명 역매핑 (필요시 사용)
        
        Args:
            agent_name (str): Agent 이름
        
        Returns:
            Dict[str, str]: 표준 도구명 → 원본 도구명 매핑
        
        Example:
            >>> ToolNameMapper.get_reverse_mapping('gemini')
            {'read_email': 'readEmail', 'send_email': 'sendEmail', ...}
        """
        agent_name_lower = agent_name.lower()
        
        if agent_name_lower not in ToolNameMapper.MAPPINGS:
            raise ValueError(f"Unknown agent: {agent_name}")
        
        original_mapping = ToolNameMapper.MAPPINGS[agent_name_lower]
        return {v: k for k, v in original_mapping.items()}