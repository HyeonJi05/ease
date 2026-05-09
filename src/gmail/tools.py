"""
Gmail API 래퍼

기능:
1. 메일 조회 (읽지 않은 메일, 검색)
2. 메일 읽기
3. 메일 전송
4. 메일 삭제
5. 메일 읽음 처리
"""

import base64
import mimetypes
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from typing import List, Dict, Any, Optional, Union
import json
from pathlib import Path


SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


class GmailTools:
    """Gmail API 래퍼"""
    
    _attacker_email_cache = None  # attacker 이메일 캐싱 (클래스 변수)
    
    def __init__(self, credentials: Union[Credentials, str]):
        """
        GmailTools 초기화
        
        Args:
            credentials: Google OAuth 2.0 크레덴셜 또는 계정 타입 ('victim' or 'attacker')
        """
        # 문자열이면 계정 타입으로 간주하고 credentials 로드
        if isinstance(credentials, str):
            account_type = credentials
            credentials = self._load_credentials(account_type)
            self.account_type = account_type
        else:
            self.account_type = 'unknown'
        
        self.credentials = credentials
        self.service = build('gmail', 'v1', credentials=credentials)
        self._email = None
    
    def _load_credentials(self, account_type: str) -> Credentials:
        """
        계정 타입에 따라 credentials 로드
        
        Args:
            account_type: 'victim' or 'attacker'
        
        Returns:
            Credentials 객체
        """
        # 프로젝트 루트 경로
        project_root = Path(__file__).parent.parent.parent
        
        credentials_file = project_root / f'credentials_{account_type}.json'
        token_file = project_root / f'token_{account_type}.json'
        
        creds = None
        
        # 기존 토큰 로드
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
        
        # 토큰이 없거나 만료된 경우
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not credentials_file.exists():
                    raise FileNotFoundError(
                        f"credentials 파일을 찾을 수 없습니다: {credentials_file}\n"
                        f"Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 다운로드하세요."
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)
            
            # 토큰 저장
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
        
        return creds
    
    def get_unread_emails(self, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        읽지 않은 메일 목록 조회
        
        Args:
            max_results: 최대 조회 개수 (기본: 10)
        
        Returns:
            List[Dict]: 메일 목록
            [
                {
                    'id': '...',
                    'threadId': '...',
                    'sender': 'attacker@evil.com',
                    'subject': '...',
                    'snippet': '...',
                    'internalDate': '...'
                },
                ...
            ]
        """
        
        try:
            # 읽지 않은 메일 검색
            results = self.service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            # 메일 상세 정보 조회
            email_list = []
            for msg in messages:
                email_detail = self.read_email(msg['id'])
                if email_detail:
                    email_list.append(email_detail)
            
            return email_list
        
        except Exception as e:
            print(f"❌ 읽지 않은 메일 조회 오류: {e}")
            return []
    

    def get_email(self) -> str:
        """
        현재 로그인된 Gmail 이메일 주소 반환
        
        Returns:
            str: 이메일 주소 (예: 'user@gmail.com')
        """
        if self._email is not None:
            return self._email
        
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            self._email = profile.get('emailAddress', '')
            print(f"✅ 현재 계정: {self._email}")
            return self._email
        
        except Exception as e:
            print(f"❌ 이메일 주소 조회 오류: {e}")
            return ''

    def search_emails(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        메일 검색
        
        Args:
            query: 검색 쿼리 (예: 'from:attacker@evil.com')
            max_results: 최대 조회 개수
        
        Returns:
            List[Dict]: 검색 결과 메일 목록
        """
        
        try:
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            email_list = []
            for msg in messages:
                email_detail = self.read_email(msg['id'])
                if email_detail:
                    email_list.append(email_detail)
            
            return email_list
        
        except Exception as e:
            print(f"❌ 메일 검색 오류: {e}")
            return []
    
    def read_email(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        메일 내용 읽기
        
        Args:
            message_id: 메일 ID
        
        Returns:
            Dict: 메일 상세 정보
            {
                'id': '...',
                'threadId': '...',
                'sender': 'attacker@evil.com',
                'to': 'user@gmail.com',
                'subject': '...',
                'snippet': '...',
                'body': '...',
                'internalDate': '...'
            }
        """
        
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload']['headers']
            
            # 헤더에서 정보 추출
            sender = self._get_header_value(headers, 'From')
            to = self._get_header_value(headers, 'To')
            subject = self._get_header_value(headers, 'Subject')
            snippet = message.get('snippet', '')
            
            # 본문 추출
            body = self._get_body(message['payload'])
            
            return {
                'id': message['id'],
                'threadId': message['threadId'],
                'sender': sender,
                'to': to,
                'subject': subject,
                'snippet': snippet,
                'body': body,
                'internalDate': message.get('internalDate')
            }
        
        except Exception as e:
            print(f"❌ 메일 읽기 오류 (ID: {message_id}): {e}")
            return None
    
    def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: Optional[str] = None,
        bcc: Optional[str] = None,
        attachments: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        메일 전송
        
        Args:
            to: 수신자 이메일 주소
            subject: 메일 제목
            body: 메일 본문
            cc: 참조 (선택)
            bcc: 숨은 참조 (선택)
            attachments: 첨부 파일 경로 리스트 (선택)
        
        Returns:
            Dict: {'success': bool, 'message_id': str or None, 'error': str or None}
        """
        
        try:
            # 🔄 테스트용: 플레이스홀더 이메일을 실제 attacker 이메일로 치환
            placeholder_emails = [
                'contact@contact.com',
                'attacker@evil.com',
                'attacker@gmail.com',
                'hacker@evil.com',
                'test@test.com',
                'malicious@example.com'
            ]
            
            if to in placeholder_emails:
                # attacker 이메일을 토큰에서 동적으로 조회 (캐싱)
                if GmailTools._attacker_email_cache is None:
                    try:
                        attacker_gmail = GmailTools('attacker')
                        GmailTools._attacker_email_cache = attacker_gmail.get_email()
                    except Exception as e:
                        print(f"⚠️ Attacker 이메일 조회 실패: {e}")
                
                if GmailTools._attacker_email_cache:
                    print(f"🔄 이메일 치환: {to} → {GmailTools._attacker_email_cache}")
                    to = GmailTools._attacker_email_cache
            
            # 메일 구성
            message = MIMEMultipart()
            message['To'] = to
            message['Subject'] = subject
            if cc:
                message['Cc'] = cc
            if bcc:
                message['Bcc'] = bcc
            message.attach(MIMEText(body, 'plain'))
            
            # 첨부 파일 추가
            if attachments:
                for file_path in attachments:
                    self._attach_file(message, file_path)
            
            # 메일 전송
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            print(f"✅ 메일 전송 성공: {to}")
            return {
                'success': True,
                'message_id': result.get('id'),
                'error': None
            }
        
        except Exception as e:
            print(f"❌ 메일 전송 오류: {e}")
            return {
                'success': False,
                'message_id': None,
                'error': str(e)
            }
    
    def delete_email(self, message_id: str) -> bool:
        """
        메일 삭제
        
        Args:
            message_id: 메일 ID
        
        Returns:
            bool: 성공 여부
        """
        
        try:
            self.service.users().messages().delete(
                userId='me',
                id=message_id
            ).execute()
            
            print(f"✅ 메일 삭제 성공: {message_id}")
            return True
        
        except Exception as e:
            print(f"❌ 메일 삭제 오류: {e}")
            return False
    
    def mark_as_read(self, message_id: str) -> bool:
        """
        메일을 읽음으로 표시
        
        Args:
            message_id: 메일 ID
        
        Returns:
            bool: 성공 여부
        """
        
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            print(f"✅ 메일 읽음 표시: {message_id}")
            return True
        
        except Exception as e:
            print(f"❌ 읽음 표시 오류: {e}")
            return False
    
    def trash_email(self, message_id: str) -> bool:
        """
        메일을 휴지통으로 이동
        
        Args:
            message_id: 메일 ID
        
        Returns:
            bool: 성공 여부
        """
        
        try:
            self.service.users().messages().trash(
                userId='me',
                id=message_id
            ).execute()
            
            print(f"✅ 메일 휴지통 이동: {message_id}")
            return True
        
        except Exception as e:
            print(f"❌ 휴지통 이동 오류: {e}")
            return False
    
    # 헬퍼 메서드
    
    def _get_header_value(self, headers: List[Dict], name: str) -> str:
        """헤더에서 값 추출"""
        
        for header in headers:
            if header['name'] == name:
                return header['value']
        
        return ''
    
    def _get_body(self, payload: Dict) -> str:
        """메일 본문 추출"""
        
        if 'parts' in payload:
            # multipart 메일
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8')
        else:
            # 단순 텍스트 메일
            data = payload['body'].get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8')
        
        return ''
    
    def _attach_file(self, message: MIMEMultipart, file_path: str):
        """첨부 파일 추가"""
        
        try:
            with open(file_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
            
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename= {file_path}')
            message.attach(part)
        
        except Exception as e:
            print(f"❌ 파일 첨부 오류 ({file_path}): {e}")
    
    def get_service(self):
        """Gmail API 서비스 객체 반환 (고급 사용)"""
        return self.service