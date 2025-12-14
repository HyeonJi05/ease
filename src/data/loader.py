"""
공격 데이터 로더 - attack_dataset.csv 사용

기능:
1. attack_dataset.csv 로드 (6개 공격 유형)
2. 유형별 필터링 및 랜덤 추출
3. 이메일 필드명을 TestRunner 호환 형식으로 변환
"""

import csv
from typing import List, Dict, Any, Optional
from pathlib import Path
import random


# 공격 유형 정의 (fallback용 - 실제 개수는 CSV에서 동적으로 로드)
ATTACK_TYPES = {
    1: {'name': '대화 경계 위조형', 'desc': 'Conversation Boundary Forgery'},
    2: {'name': '역할/경계 토큰 주입형', 'desc': 'Role/Boundary Token Injection'},
    3: {'name': '메일-묶음 전달형', 'desc': 'Email Bundle Forwarding'},
    4: {'name': '포맷/마크업 경계 위조형', 'desc': 'Format/Markup Boundary Forgery'},
    5: {'name': '워크플로우/절차 위장형', 'desc': 'Workflow/Procedure Disguise'},
    6: {'name': '툴 호출 DSL/페이로드 직접 주입형', 'desc': 'Tool Call DSL/Payload Direct Injection'},
}


class AttackDataLoader:
    """공격 데이터 로더 - CSV 기반"""
    
    def __init__(self, data_file: Optional[str] = None):
        """
        AttackDataLoader 초기화
        
        Args:
            data_file: CSV 데이터 파일 경로
                      없으면 기본 경로 사용: data/attack_dataset.csv
        """
        if data_file is None:
            project_root = Path(__file__).parent.parent.parent
            self.data_file = project_root / 'data' / 'attack_dataset.csv'
        else:
            self.data_file = Path(data_file)
        
        self.attacks = []
        self.metadata = {}
    
    def load(self, 
             types: Optional[List[int]] = None, 
             samples_per_type: Optional[int] = None,
             total_samples: Optional[int] = None,
             random_seed: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        공격 데이터 로드 (유형별 필터링 및 랜덤 추출)
        
        Args:
            types: 선택할 유형 번호 리스트 (None이면 전체)
            samples_per_type: 유형별 추출 샘플 수 (None이면 전체)
            total_samples: 전체에서 랜덤 추출할 샘플 수 (samples_per_type과 함께 사용 불가)
            random_seed: 랜덤 시드 (재현성)
        
        Returns:
            List[Dict]: 공격 샘플 리스트
        """
        if random_seed is not None:
            random.seed(random_seed)
        
        # CSV 파일 존재 확인
        if not self.data_file.exists():
            print(f"❌ 데이터 파일 없음: {self.data_file}")
            return []
        
        try:
            all_attacks = self._load_csv()
            
            # 유형 필터링
            if types:
                all_attacks = [a for a in all_attacks if a.get('type') in types]
            
            # 샘플 추출
            if samples_per_type is not None:
                # 유형별로 랜덤 추출
                result = []
                type_groups = {}
                for attack in all_attacks:
                    t = attack.get('type')
                    if t not in type_groups:
                        type_groups[t] = []
                    type_groups[t].append(attack)
                
                for t, attacks in type_groups.items():
                    sampled = random.sample(attacks, min(samples_per_type, len(attacks)))
                    result.extend(sampled)
                
                self.attacks = result
            elif total_samples is not None:
                # 전체에서 랜덤 추출
                self.attacks = random.sample(all_attacks, min(total_samples, len(all_attacks)))
            else:
                self.attacks = all_attacks
            
            # 인덱스 재할당
            for idx, attack in enumerate(self.attacks):
                attack['index'] = idx
            
            self.metadata['total_samples'] = len(self.attacks)
            self.metadata['data_file'] = str(self.data_file)
            
            print(f"✅ 데이터 로드 성공: {len(self.attacks)}개 샘플")
            
            return self.attacks
        
        except Exception as e:
            print(f"❌ 데이터 로드 오류: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _load_csv(self) -> List[Dict[str, Any]]:
        """CSV 파일에서 공격 데이터 로드"""
        attacks = []
        
        try:
            with open(self.data_file, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for idx, row in enumerate(reader):
                    attack_type = int(row.get('type', 0)) if row.get('type', '').isdigit() else 0
                    
                    attack = {
                        'index': idx,
                        'email_subject': row.get('subject', ''),
                        'email_body': row.get('body', ''),
                        'full_text': row.get('full_text', ''),
                        'cluster': row.get('cluster', ''),
                        'type': attack_type,
                        'type_desc': row.get('type_desc', ''),
                        'attack_type': 'indirect_prompt_injection',
                        'source': 'attack_dataset.csv'
                    }
                    
                    attacks.append(attack)
            
            return attacks
        
        except Exception as e:
            print(f"❌ CSV 파일 로드 오류: {e}")
            return []
    
    def get_type_stats(self) -> Dict[int, Dict[str, Any]]:
        """유형별 통계 반환"""
        if not self.data_file.exists():
            return {}
        
        all_attacks = self._load_csv()
        stats = {}
        
        for attack in all_attacks:
            t = attack.get('type')
            if t not in stats:
                stats[t] = {
                    'count': 0,
                    'name': attack.get('type_desc', ATTACK_TYPES.get(t, {}).get('name', f'Type {t}'))
                }
            stats[t]['count'] += 1
        
        return stats
    
    def get_random_sample(self, count: int = 1, types: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        """무작위 샘플 선택"""
        return self.load(types=types, total_samples=count)
    
    def reset(self):
        """데이터 초기화"""
        self.attacks = []
        self.metadata = {}