#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试FastGPT返回格式
"""
import requests
import os
import json
from dotenv import load_dotenv
from pathlib import Path

# 加载环境变量
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / '.env'
load_dotenv(ENV_FILE, override=True)

base_url = os.getenv('FASTGPT_BASE_URL', 'http://60.204.240.91:3000')
api_key = os.getenv('INTERVIEW_FASTGPT_API_KEY', '')

print("=" * 70)
print("  测试FastGPT返回格式")
print("=" * 70)
print(f"\n[配置]")
print(f"  Base URL: {base_url}")
print(f"  API Key: {api_key[:30]}...")

# 测试请求
test_url = f"{base_url}/api/v1/chat/completions"

system_prompt = '''你是一个专业的面试官，正在进行模拟面试。

【重要：返回格式要求】
你必须严格按照以下JSON格式返回回复（不要包含其他内容）：
{
  "current_question": "下一个面试问题",
  "answer_brief_evaluation": "对用户刚才回答的简短评价"
}

【面试规则】
1. 根据用户的回答提出相关的面试问题
2. 保持对话流畅自然，问题要由浅入深
3. 对每个回答给出简短的评价（1-2句话）
4. 适时追问细节，了解技术深度
5. 保持专业、友好的态度

【特殊情况】
- 如果这是第一次对话，answer_brief_evaluation可以为空字符串
- current_question必须始终包含一个问题
- 确保JSON格式正确，可以被直接解析'''

test_data = {
    'chatId': 'test_format_001',
    'stream': False,
    'messages': [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': '你好，我想面试Java开发岗位'}
    ]
}

headers = {
    'Authorization': f'Bearer {api_key}',
    'Content-Type': 'application/json'
}

print(f"\n[测试请求]")
print(f"  URL: {test_url}")
print(f"  消息数: {len(test_data['messages'])}")
print(f"\n发送请求...")

try:
    response = requests.post(test_url, json=test_data, headers=headers, timeout=300)
    print(f"\n[响应信息]")
    print(f"  状态码: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"  响应keys: {list(result.keys())}")

        if 'choices' in result and len(result['choices']) > 0:
            ai_content = result['choices'][0].get('message', {}).get('content', '')
            print(f"\n[AI响应内容]")
            print("-" * 70)
            print(ai_content)
            print("-" * 70)

            # 测试JSON解析
            print(f"\n[JSON解析测试]")
            try:
                # 尝试1: 直接解析
                cleaned = ai_content.strip()
                cleaned = cleaned.replace('```json', '').replace('```', '').strip()
                cleaned = cleaned.replace('\n', ' ')

                obj = json.loads(cleaned)
                print(f"✓ JSON解析成功")
                print(f"  current_question: {obj.get('current_question', 'N/A')[:50]}...")
                print(f"  answer_brief_evaluation: {obj.get('answer_brief_evaluation', 'N/A')[:50]}...")

                # 验证字段
                if 'current_question' in obj and 'answer_brief_evaluation' in obj:
                    print(f"\n✓ 格式验证通过：包含必需字段")
                else:
                    print(f"\n✗ 格式验证失败：缺少必需字段")

            except json.JSONDecodeError as e:
                print(f"✗ JSON解析失败: {e}")

                # 尝试正则提取
                print(f"\n尝试正则提取...")
                import re
                q = re.search(r'"current_question"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', ai_content)
                a = re.search(r'"answer_brief_evaluation"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', ai_content)

                if q or a:
                    print(f"✓ 正则提取成功")
                    if q:
                        print(f"  current_question: {q.group(1)[:50]}...")
                    if a:
                        print(f"  answer_brief_evaluation: {a.group(1)[:50]}...")
                else:
                    print(f"✗ 正则提取失败")

        print(f"\n✅ 测试完成")
    else:
        print(f"\n❌ 请求失败: {response.status_code}")
        print(f"响应内容: {response.text}")

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
