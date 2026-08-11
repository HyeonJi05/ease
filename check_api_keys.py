"""
LLM API 키 활성 확인 스크립트

.env 파일의 API 키가 정상 작동하는지 간단한 요청을 보내 확인합니다.

사용법:
    python check_api_keys.py
    python check_api_keys.py --llm claude
    python check_api_keys.py --llm gpt
    python check_api_keys.py --llm gemini
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# .env 로드
load_dotenv(Path(__file__).parent / '.env')


def check_claude():
    """Claude API 확인"""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("  ❌ ANTHROPIC_API_KEY가 .env에 설정되지 않았습니다.")
        return False
    
    print(f"  🔑 키: {api_key[:12]}...{api_key[-4:]}")
    
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        text = response.content[0].text
        print(f"  ✅ Claude 응답: {text.strip()}")
        print(f"     모델: {response.model}")
        return True
    except Exception as e:
        print(f"  ❌ Claude 오류: {e}")
        return False


def check_gpt():
    """GPT API 확인"""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("  ❌ OPENAI_API_KEY가 .env에 설정되지 않았습니다.")
        return False
    
    print(f"  🔑 키: {api_key[:12]}...{api_key[-4:]}")
    
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        text = response.choices[0].message.content
        print(f"  ✅ GPT-4o 응답: {text.strip()}")
        print(f"     모델: {response.model}")
        return True
    except Exception as e:
        print(f"  ❌ GPT-4o 오류: {e}")
        return False


def check_gemini():
    """Gemini API 확인"""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("  ❌ GEMINI_API_KEY가 .env에 설정되지 않았습니다.")
        return False
    
    print(f"  🔑 키: {api_key[:12]}...{api_key[-4:]}")
    
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents='Say OK'
        )
        text = response.text
        print(f"  ✅ Gemini 응답: {text.strip()}")
        return True
    except Exception as e:
        print(f"  ❌ Gemini 오류: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description='LLM API 키 활성 확인')
    parser.add_argument('--llm', choices=['claude', 'gpt', 'gemini'],
                        help='특정 LLM만 확인 (미지정 시 전부)')
    args = parser.parse_args()
    
    checks = {
        'claude': ('Claude (claude-sonnet-4-5-20250929)', check_claude),
        'gpt': ('GPT-4o', check_gpt),
        'gemini': ('Gemini 2.0 Flash', check_gemini),
    }
    
    if args.llm:
        targets = {args.llm: checks[args.llm]}
    else:
        targets = checks
    
    print(f"\n{'='*50}")
    print(f"🔍 LLM API 키 확인")
    print(f"{'='*50}")
    
    results = {}
    for key, (name, func) in targets.items():
        print(f"\n📌 {name}")
        results[key] = func()
    
    # 요약
    print(f"\n{'='*50}")
    print(f"📊 결과 요약")
    print(f"{'='*50}")
    for key, (name, _) in targets.items():
        status = "✅ 정상" if results[key] else "❌ 실패"
        print(f"  {name}: {status}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\n  {passed}/{total} 통과")
    print(f"{'='*50}\n")
    
    if passed < total:
        sys.exit(1)


if __name__ == '__main__':
    main()