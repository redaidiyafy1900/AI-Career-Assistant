#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能职业发展助手 - Python 版本
基于 Flask 的 AI 模拟面试 + 求职助理系统
"""

import asyncio
import sys

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import re
import requests
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
from backend.utils.logger import logger

# 加载环境变量（显式指定.env路径）
PROJECT_ROOT = Path(__file__).parent
ENV_FILE = PROJECT_ROOT / '.env'
load_dotenv(ENV_FILE, override=True)

# 初始化 Flask 应用
app = Flask(__name__, static_folder='frontend')
CORS(app, origins=['*'])

# ==================== 配置管理 ====================

class Config:
    PORT = int(os.getenv('PORT', 3002))
    # 豆包 API 配置（面试功能 - 文字面试和真人视频面试共用）
    INTERVIEW_DOBAO_URL = os.getenv('INTERVIEW_DOBAO_URL', 'https://ark.cn-beijing.volces.com/api/v3/chat/completions')
    INTERVIEW_DOBAO_API_KEY = os.getenv('INTERVIEW_DOBAO_API_KEY', 'af6ff3bf-f66a-4652-8043-0cc1142abdd4')
    INTERVIEW_DOBAO_MODEL = os.getenv('INTERVIEW_DOBAO_MODEL', 'ep-20260329183523-7ns5h')
    MAX_FILE_SIZE = int(os.getenv('MAX_FILE_SIZE', 5242880))
    UPLOAD_FOLDER = Path('backend/uploads')
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

config = Config()

# 打印配置信息用于调试
print(f"[配置] 项目根目录: {PROJECT_ROOT}")
print(f"[配置] .env文件路径: {ENV_FILE}")
print(f"[配置] .env文件存在: {ENV_FILE.exists()}")
print(f"[配置] INTERVIEW_DOBAO_URL: {config.INTERVIEW_DOBAO_URL}")
print(f"[配置] INTERVIEW_DOBAO_API_KEY: {'已配置' if config.INTERVIEW_DOBAO_API_KEY else '未配置'}")
print(f"[配置] INTERVIEW_DOBAO_MODEL: {config.INTERVIEW_DOBAO_MODEL}")

# 懒加载后端模块
_db = None
_backend_config = None

def get_db():
    global _db
    if _db is None:
        from backend.storage.database import Database
        _db = Database()
    return _db

def get_backend_config():
    global _backend_config
    if _backend_config is None:
        from backend.core.config import Config as BackendConfig
        _backend_config = BackendConfig.load()
    return _backend_config

# ==================== 工具函数 ====================

def log_info(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] INFO: {message}")

def log_error(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {message}")

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'pdf', 'doc', 'docx'}

# ==================== 静态文件服务 ====================

@app.route('/')
def index():
    return send_from_directory('frontend', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    if os.path.exists(os.path.join('frontend', filename)):
        return send_from_directory('frontend', filename)
    return jsonify({'error': '文件不存在'}), 404

@app.route('/photo/<path:filename>')
def photo_files(filename):
    return send_from_directory('photo', filename)

@app.route('/video/<path:filename>')
def video_files(filename):
    return send_from_directory('视频', filename)

@app.route('/uploads/<path:filename>')
def upload_files(filename):
    """提供上传文件的访问"""
    return send_from_directory(str(config.UPLOAD_FOLDER), filename)

# ==================== 面试降级响应 ====================

FALLBACK_QUESTIONS = [
    "请简要介绍一下你自己，包括你的教育背景和专业技能。",
    "你为什么选择应聘这个岗位？你对这个职位有什么了解？",
    "请描述一下你在校期间参与过的最有成就感的项目或实习经历。",
    "你在团队合作中通常扮演什么角色？能否举一个具体的例子？",
    "你认为自己最大的优点和需要改进的地方分别是什么？",
    "你对未来3-5年的职业规划是什么？",
    "当遇到技术难题或工作压力时，你通常如何应对？",
    "你有什么问题想问我（面试官）的吗？",
]

FALLBACK_EVALUATIONS = [
    "回答得不错，思路清晰。",
    "很好的回答，能够结合具体经历。",
    "回答比较完整，但可以再深入一些细节。",
    "不错的思路，建议多举一些实际案例来支撑。",
    "回答有条理，继续保持。",
]

import random

def generate_fallback_response(messages, job_info, interview_type):
    """当FastGPT超时时生成预设的面试问题"""
    # 根据消息数量选择不同的问题
    msg_count = len([m for m in messages if m.get('role') == 'user'])
    question_idx = min(msg_count, len(FALLBACK_QUESTIONS) - 1)
    question = FALLBACK_QUESTIONS[question_idx]
    evaluation = FALLBACK_EVALUATIONS[random.randint(0, len(FALLBACK_EVALUATIONS) - 1)]

    # 如果有岗位信息，尝试个性化问题
    if job_info and msg_count >= 2:
        title = job_info.get('title', '')
        if '开发' in title or '工程师' in title:
            question = "请谈谈你对代码质量和软件工程规范的理解，你在项目中是如何实践的？"
        elif '数据' in title or '算法' in title:
            question = "请描述一个你处理过的数据分析或算法优化问题，你是如何解决的？"
        elif '销售' in title or '市场' in title:
            question = "如果你需要在一个新区域开拓市场，你会如何制定策略？"
        elif '财务' in title or '会计' in title:
            question = "请简述你对财务报表分析的理解，以及你在实习中接触过的相关经验。"
        elif '人力' in title or 'HR' in title:
            question = "你认为优秀的HR应该具备哪些核心能力？请结合你的理解谈谈。"

    return f"{evaluation}\n\n{question}"


# ==================== 面试相关 API ====================

@app.route('/api/interview-chat', methods=['POST'])
def interview_chat():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据为空'}), 400

        messages = data.get('messages', [])
        session_id = data.get('sessionId', f'interview_{int(time.time())}')
        job_info = data.get('job')  # Optional: {title, company, description, full_jd}
        interview_type = data.get('type', 'text')  # 'text' or 'video' (real interview)

        if not messages:
            return jsonify({'success': False, 'error': '需要提供对话消息'}), 400

        # Build system prompt, optionally including job info
        # 文字面试：温和鼓励风格
        system_content = '''你是一个专业的AI面试官，专注于挖掘面试者岗位适配能力。

【角色设定】
你是一名拥有10年经验的资深HR面试官，擅长根据候选人的专业背景和目标岗位进行针对性面试。你的风格是温和、鼓励、建设性的。

【任务指令 - 文字模拟面试】
1. 仔细分析用户的回答，根据内容提出有深度的后续问题
2. 面试问题要由浅入深，从基础知识逐步深入到实际应用
3. 对每个回答给出中肯的简短评价（1-2句话），先肯定亮点，再温和指出可改进点
4. 适时追问技术细节，了解候选人的实际掌握深度
5. 保持专业、友好、鼓励的态度，营造轻松但专业的面试氛围
6. 当用户发送"自我介绍"或"请做自我介绍"或"面试开始"时，请提问：
   "你好！请做一个完整的自我介绍，包括你的教育背景、专业技能、实习经历和项目经验。注意：请完整叙述，不要省略关键信息。"

【面试流程建议】
- 第1轮：请用户自我介绍，然后基于自我介绍内容提问
- 第2-6轮：深入挖掘经历细节、技术能力、软技能
- 第7轮：总结性评价，生成评分报告

【重要：返回格式要求】
你必须严格按照以下JSON格式返回回复（不要包含其他内容，不要使用markdown代码块）：
{
  "answer_brief_evaluation": "对上一轮回答的简短评价。格式：亮点总结（第二人称，含具体细节）+ 待补充点（第二人称，温和带鼓励）。如果是第一轮，此字段可为空字符串。",
  "current_question": "全新生成的问题。需关联岗位核心场景与面试者具体经历，具有创新角度。"
}

【输出规则】
- 如果这是第一次对话（用户尚未回答），answer_brief_evaluation可以为空字符串
- current_question必须始终包含一个具体问题
- 确保JSON格式正确，可以被json.loads()直接解析
- 评价要具体，避免空泛的"很好""不错"等
- 问题要有针对性，基于用户之前的回答内容
- 保持温和鼓励的语气，帮助用户建立信心'''

        if job_info:
            title = job_info.get('title', '')
            company = job_info.get('company', '')
            description = job_info.get('description', '') or job_info.get('full_jd', '')
            job_context = f"\n\n【目标岗位信息】\n岗位：{title}\n公司：{company}"
            if description:
                job_context += f"\n岗位描述：{description[:2000]}"
            system_content += job_context

        request_data = {
            'chatId': session_id,
            'stream': False,
            'messages': [
                {'role': 'system', 'content': system_content},
                *messages
            ]
        }

        # 使用豆包 API（文字面试和真人视频面试共用）
        api_url = config.INTERVIEW_DOBAO_URL
        api_key = config.INTERVIEW_DOBAO_API_KEY
        model = config.INTERVIEW_DOBAO_MODEL
        
        if interview_type == 'video':
            print(f"[API调用] 真人视频面试 - 发送豆包API请求")
            print(f"  URL: {api_url}")
            print(f"  Model: {model}")
            print(f"  Session ID: {session_id}")
            print(f"  消息数: {len(messages)}")
        else:
            print(f"[API调用] 文字面试 - 发送豆包API请求")
            print(f"  URL: {api_url}")
            print(f"  Model: {model}")
            print(f"  Session ID: {session_id}")
            print(f"  消息数: {len(messages)}")

        # 尝试请求豆包API，带重试和降级
        max_retries = 1
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                print(f"[API调用] 第{attempt+1}次尝试发送豆包API请求")
                
                # 构建豆包API请求格式
                doubao_headers = {
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json'
                }
                
                doubao_payload = {
                    'model': model,
                    'messages': request_data['messages'],
                    'temperature': 0.7,
                    'max_tokens': 2000,
                    'stream': False
                }
                
                response = requests.post(
                    api_url,
                    json=doubao_payload,
                    headers=doubao_headers,
                    timeout=120  # 豆包API响应更快，设置为2分钟
                )
                response.raise_for_status()
                result = response.json()
                
                # 转换豆包API响应格式为原有格式
                # 豆包格式: {"choices": [{"message": {"content": "..."}}]}
                # 与FastGPT格式兼容，无需转换
                break  # 成功则跳出重试循环
            except requests.exceptions.Timeout:
                print(f"[警告] 豆包API第{attempt+1}次请求超时（120秒）")
                last_error = 'timeout'
                if attempt < max_retries:
                    print("[重试] 等待3秒后重试...")
                    time.sleep(3)
                continue
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                print(f"[错误] 豆包API请求失败: {e}")
                break  # 其他错误不重试
        else:
            # 所有重试都失败了，使用降级响应
            print(f"[降级] 豆包API多次请求失败({last_error})，返回预设面试问题")
            fallback_msg = generate_fallback_response(messages, job_info, interview_type)
            return jsonify({
                'success': True,
                'message': fallback_msg,
                'sessionId': session_id,
                'fallback': True,
                'timestamp': datetime.now().isoformat()
            })

        print(f"[API响应] 请求成功")
        print(f"  状态码: {response.status_code}")
        print(f"  响应keys: {list(result.keys())}")

        ai_content = ''
        if 'choices' in result and len(result['choices']) > 0:
            ai_content = result['choices'][0].get('message', {}).get('content', '')

            # 预处理：确保AI返回正确的JSON格式
            if ai_content and ('{' in ai_content or '"' in ai_content):
                print(f"[预处理] AI响应包含JSON标记，尝试清理")

                # 移除markdown代码块
                cleaned = ai_content.strip()
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:]
                if cleaned.startswith('```'):
                    cleaned = cleaned[3:]
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()

                # 安全检查：清理后不能为空
                if not cleaned:
                    print(f"[预处理] 清理后内容为空，保留原始响应（长度: {len(ai_content)}）")
                    # 不修改 ai_content，继续使用原始内容
                elif len(cleaned) < 10:
                    print(f"[预处理] 清理后内容过短({len(cleaned)}字符)，可能是截断的JSON，保留原始响应")
                    # 内容太短不可能是有效对话JSON，保留原始
                else:
                    # 验证是否为有效JSON
                    try:
                        obj = json.loads(cleaned)

                        # 判断是报告格式的JSON还是对话格式的JSON
                        if 'overall_score' in obj or 'quantitative_assessment' in obj:
                            print(f"[预处理] 检测到面试报告格式JSON，保留原始内容")
                            print(f"  overall_score: {obj.get('overall_score')}")
                            print(f"  score_level: {obj.get('score_level')}")
                            ai_content = cleaned
                        elif 'current_question' in obj and 'answer_brief_evaluation' in obj:
                            print(f"[预处理] 对话格式JSON验证通过")
                            print(f"  current_question存在: {'是' if obj.get('current_question') else '否'}")
                            print(f"  answer_brief_evaluation存在: {'是' if obj.get('answer_brief_evaluation') else '否'}")

                            parts = []
                            if obj.get('answer_brief_evaluation'):
                                parts.append(obj['answer_brief_evaluation'])
                            if obj.get('current_question'):
                                parts.append(obj['current_question'])

                            if parts:
                                ai_content = '\n\n'.join(parts)
                                print(f"[预处理] 已提取纯文本内容，长度: {len(ai_content)} 字符")
                            else:
                                ai_content = cleaned
                                print(f"[预处理] 字段都为空，保留JSON格式")
                        else:
                            print(f"[预处理] JSON缺少必需字段(现有: {list(obj.keys())})，保留原始响应")
                    except json.JSONDecodeError as e:
                        print(f"[预处理] JSON解析失败: {e}，保留原始响应（长度: {len(ai_content)}）")

        return jsonify({
            'success': True,
            'message': ai_content,
            'sessionId': session_id,
            'timestamp': datetime.now().isoformat()
        })

    except requests.exceptions.Timeout:
        print(f"[错误] FastGPT API请求超时（600秒）")
        print(f"  Session ID: {session_id}")
        print(f"  消息数: {len(messages)}")
        # 超时时也返回降级响应，避免前端完全失败
        fallback_msg = generate_fallback_response(messages, job_info, interview_type)
        return jsonify({
            'success': True,
            'message': fallback_msg,
            'sessionId': session_id,
            'fallback': True,
            'timestamp': datetime.now().isoformat()
        })
    except requests.exceptions.RequestException as e:
        error_response = None
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_response = e.response.json()
                print(f"[错误] FastGPT API调用失败")
                print(f"  状态码: {e.response.status_code}")
                print(f"  错误响应: {json.dumps(error_response, indent=2, ensure_ascii=False)}")
            except:
                error_response = e.response.text
                print(f"[错误] FastGPT API调用失败")
                print(f"  状态码: {e.response.status_code}")
                print(f"  错误文本: {error_response}")
        else:
            print(f"[错误] 请求异常: {e}")
        return jsonify({'success': False, 'error': 'AI 服务调用失败', 'message': str(e), 'details': error_response}), 500
    except Exception as e:
        print(f"[错误] 未知错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': '服务器内部错误', 'message': str(e)}), 500

# ==================== 面试记忆 API ====================

@app.route('/api/interview/save', methods=['POST'])
def interview_save():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据为空'}), 400
        db = get_db()
        session_id = db.insert_interview_session(data)
        return jsonify({'success': True, 'id': session_id})
    except Exception as e:
        log_error(f"保存面试记录失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interview/history', methods=['GET'])
def interview_history():
    try:
        db = get_db()
        limit = int(request.args.get('limit', 50))
        sessions = db.get_interview_sessions(limit=limit)
        for s in sessions:
            if isinstance(s.get('messages'), str):
                try:
                    s['messages'] = json.loads(s['messages'])
                except Exception:
                    s['messages'] = []
            if isinstance(s.get('feedback_json'), str):
                try:
                    s['feedback_json'] = json.loads(s['feedback_json'])
                except Exception:
                    s['feedback_json'] = {}
        return jsonify({'success': True, 'sessions': sessions})
    except Exception as e:
        log_error(f"获取面试历史失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interview/session/<session_id>', methods=['GET'])
def interview_session_get(session_id):
    try:
        db = get_db()
        session = db.get_interview_session(session_id)
        if not session:
            return jsonify({'success': False, 'error': '面试记录不存在'}), 404
        if isinstance(session.get('messages'), str):
            try:
                session['messages'] = json.loads(session['messages'])
            except Exception:
                session['messages'] = []
        if isinstance(session.get('feedback_json'), str):
            try:
                session['feedback_json'] = json.loads(session['feedback_json'])
            except Exception:
                session['feedback_json'] = {}
        return jsonify({'success': True, 'session': session})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/interview/session/<session_id>', methods=['DELETE'])
def interview_session_delete(session_id):
    try:
        db = get_db()
        db.delete_interview_session(session_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def clean_image_references(text):
    """过滤掉各种格式的图片引用，避免显示 @image:image.png 等问题"""
    if not text:
        return text
    
    # 过滤 Markdown 图片引用 ![xxx](xxx)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 过滤 @image:xxx 格式
    text = re.sub(r'@image:?\S*', '', text)
    # 过滤 ![xxx] 或 ![] 格式（空图片引用）
    text = re.sub(r'!\[\]', '', text)
    # 过滤图片URL（以常见图片扩展名结尾的链接）
    text = re.sub(r'https?://\S+\.(?:png|jpg|jpeg|gif|webp|bmp|svg)', '', text, flags=re.IGNORECASE)
    # 清理多余的空白
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)
    
    return text.strip()


def normalize_report_format(report_data):
    """
    将AI返回的各种格式统一为蛇形命名格式（与parse_markdown_report返回格式一致）
    这样前端convertApiReportToFrontend函数可以统一处理
    """
    if not report_data:
        return report_data
    
    # 如果是AI直接返回的JSON格式（quantitative_score格式），转换为蛇形命名格式
    if 'quantitative_score' in report_data and 'qualitative_summary' in report_data:
        normalized = {}
        
        # 1. 总分
        normalized['overall_score'] = report_data.get('quantitative_score', {}).get('total_score', 50)
        
        # 2. 分数等级
        score = normalized['overall_score']
        if score >= 90:
            normalized['score_level'] = '优秀'
        elif score >= 75:
            normalized['score_level'] = '良好'
        elif score >= 60:
            normalized['score_level'] = '一般'
        else:
            normalized['score_level'] = '较差'
        
        # 3. 评分详情（转换为score_details数组格式）
        dim_scores = report_data.get('quantitative_score', {}).get('dimension_scores', {})
        normalized['score_details'] = [
            {
                'dimension': '岗位适配度',
                'weight': '40%',
                'score': f"{dim_scores.get('job_fit', 0)}/40",
                'weighted_score': dim_scores.get('job_fit', 0),
                'criteria': '根据面试表现评估'
            },
            {
                'dimension': '核心能力表现',
                'weight': '40%',
                'score': f"{dim_scores.get('core_competency', 0)}/40",
                'weighted_score': dim_scores.get('core_competency', 0),
                'criteria': '根据面试表现评估'
            },
            {
                'dimension': '成长潜力',
                'weight': '20%',
                'score': f"{dim_scores.get('growth_potential', 0)}/20",
                'weighted_score': dim_scores.get('growth_potential', 0),
                'criteria': '根据面试表现评估'
            }
        ]
        
        # 4. 优势（将字符串分割为数组）
        strengths_text = report_data.get('qualitative_summary', {}).get('strengths', '')
        if isinstance(strengths_text, str):
            # 尝试按编号或项目符号分割
            import re
            items = re.split(r'(?:\d+[.、]|\*|\-)\s*', strengths_text)
            normalized['strengths'] = [item.strip() for item in items if item.strip()] or [strengths_text]
        else:
            normalized['strengths'] = strengths_text if isinstance(strengths_text, list) else []
        
        # 5. 待提升点（将字符串分割为数组）
        improvement_text = report_data.get('qualitative_summary', {}).get('improvement_areas', '')
        if isinstance(improvement_text, str):
            items = re.split(r'(?:\d+[.、]|\*|\-)\s*', improvement_text)
            normalized['areas_for_improvement'] = [item.strip() for item in items if item.strip()] or [improvement_text]
        else:
            normalized['areas_for_improvement'] = improvement_text if isinstance(improvement_text, list) else []
        
        # 6. 建议
        normalized['suggestions'] = {}
        
        interview_advice = report_data.get('actionable_suggestions', {}).get('interview_advice', '')
        normalized['suggestions']['job_search'] = interview_advice if isinstance(interview_advice, str) else ''
        
        career_advice = report_data.get('actionable_suggestions', {}).get('career_advice', '')
        if isinstance(career_advice, str):
            items = re.split(r'(?:\d+[.、]|\*|\-)\s*', career_advice)
            normalized['suggestions']['career_growth'] = [item.strip() for item in items if item.strip()] or [career_advice]
        else:
            normalized['suggestions']['career_growth'] = career_advice if isinstance(career_advice, list) else []
        
        # 7. 对话统计（保留原值或初始化）
        if 'conversation_stats' in report_data:
            normalized['conversation_stats'] = report_data['conversation_stats']
        
        return normalized
    
    # 如果已经是蛇形命名格式（parse_markdown_report返回的格式），直接返回
    return report_data


def parse_markdown_report(markdown_text):
    """解析 Markdown 格式的面试报告"""
    import re
    
    # 先过滤掉图片引用，避免 @image:image.png 等问题
    markdown_text = clean_image_references(markdown_text)
    
    report = {
        "is_raw_markdown": False,
        "raw_markdown": markdown_text
    }
    
    # 提取总分
    total_match = re.search(r'\*\*总分\*\*.*?\|\s*\*\*(\d+)\*\*', markdown_text, re.DOTALL)
    if total_match:
        report["overall_score"] = int(total_match.group(1))
    else:
        # 尝试其他格式
        score_match = re.search(r'\|\s*总分\s*\|.*?\|\s*(\d+)\s*\|', markdown_text)
        if score_match:
            report["overall_score"] = int(score_match.group(1))
    
    # 提取评分等级
    if '强烈推荐' in markdown_text or '优秀' in markdown_text:
        report["score_level"] = "优秀"
        if "overall_score" not in report:
            report["overall_score"] = 85
    elif '良好' in markdown_text:
        report["score_level"] = "良好"
        if "overall_score" not in report:
            report["overall_score"] = 75
    elif '及格' in markdown_text:
        report["score_level"] = "及格"
        if "overall_score" not in report:
            report["overall_score"] = 65
    elif '较差' in markdown_text:
        report["score_level"] = "较差"
        if "overall_score" not in report:
            report["overall_score"] = 50
    else:
        report["score_level"] = "一般"
        if "overall_score" not in report:
            report["overall_score"] = 60
    
    # 提取评分详情
    report["score_details"] = []
    
    # 解析量化评分总览表格 - 排除总分行
    table_pattern = r'\|\s*评分维度\s*\|.*?\|\s*得分\s*\|.*?(?:\n\|[-|]+\|)*\n((?:\|[^\n]+\n)+)'
    table_match = re.search(table_pattern, markdown_text, re.DOTALL)
    if table_match:
        rows = table_match.group(1).strip().split('\n')
        for row in rows:
            cols = [c.strip().replace('**', '') for c in row.split('|') if c.strip()]
            # 跳过总分行
            if len(cols) >= 3 and '总分' not in cols[0]:
                dimension = cols[0]
                score_part = cols[2]
                score_match = re.search(r'(\d+)', score_part)
                if score_match:
                    score = int(score_match.group(1))
                    weight_match = re.search(r'(\d+)%', cols[1]) if len(cols) > 1 else None
                    weight = weight_match.group(1) + '%' if weight_match else '25%'
                    
                    # 根据维度名称确定权重
                    if '适配' in dimension or '匹配' in dimension:
                        weight = '40%'
                        max_score = 40
                    elif '能力' in dimension or '表现' in dimension:
                        weight = '40%'
                        max_score = 40
                    elif '潜力' in dimension or '成长' in dimension:
                        weight = '20%'
                        max_score = 20
                    else:
                        max_score = 25
                    
                    report["score_details"].append({
                        "dimension": dimension,
                        "weight": weight,
                        "score": f"{score}/{max_score}",
                        "weighted_score": score,
                        "criteria": cols[3] if len(cols) > 3 else ""
                    })
    
    # 如果没有解析到评分详情，使用默认
    if not report["score_details"]:
        score = report.get("overall_score", 60)
        report["score_details"] = [
            {
                "dimension": "岗位适配度",
                "weight": "40%",
                "score": f"{round(score * 0.4)}/40",
                "weighted_score": round(score * 0.4),
                "criteria": "根据面试表现评估"
            },
            {
                "dimension": "核心能力表现",
                "weight": "40%",
                "score": f"{round(score * 0.4)}/40",
                "weighted_score": round(score * 0.4),
                "criteria": "根据面试表现评估"
            },
            {
                "dimension": "成长潜力",
                "weight": "20%",
                "score": f"{round(score * 0.2)}/20",
                "weighted_score": round(score * 0.2),
                "criteria": "根据面试表现评估"
            }
        ]
    
    # 提取优势
    report["strengths"] = []
    
    # 查找"核心优势"部分下的编号列表
    strength_section = re.search(r'(?:✨\s*)?核心优势[:：]?\s*\n((?:(?:\d+[.、].+)\n?)+)', markdown_text, re.DOTALL)
    if strength_section:
        lines = strength_section.group(1).strip().split('\n')
        for line in lines:
            line = line.strip()
            # 提取编号后的内容
            match = re.match(r'\d+[.、]\s*(.+?)(?:\n|$)', line)
            if match:
                text = match.group(1).replace('**', '').strip()
                if len(text) > 5:
                    report["strengths"].append(text)
    
    # 如果没找到，尝试从一般列表中提取
    if not report["strengths"]:
        all_items = re.findall(r'(?:^|\n)\s*(?:\d+[.、]|\*)\s*(.{10,80}?)(?:\n|$)', markdown_text, re.MULTILINE)
        keywords_strength = ['技术', '经验', '能力', '优势', '清晰', '扎实', '展示', '具备', '思维', '意识']
        for item in all_items:
            item = item.strip().replace('**', '')
            if any(kw in item for kw in keywords_strength) and len(report["strengths"]) < 5:
                # 跳过标题行
                if not item.startswith('#') and '待提升' not in item and '建议' not in item[:20]:
                    report["strengths"].append(item[:100])
    
    # 如果有"待提升方向"部分，提取所有项目
    improvement_section = re.search(r'(?:📌\s*)?待提升方向[:：]?\s*\n((?:(?:\d+[.、].+)\n?)+)', markdown_text, re.DOTALL)
    if not improvement_section:
        improvement_section = re.search(r'待提升方向[:：]?\s*\n((?:(?:\d+[.、].+)\n?)+)', markdown_text, re.DOTALL)
    
    # 提取待提升点
    report["areas_for_improvement"] = []
    
    if improvement_section:
        lines = improvement_section.group(1).strip().split('\n')
        for line in lines:
            line = line.strip()
            match = re.match(r'\d+[.、]\s*(.+?)(?:\n|$)', line)
            if match:
                text = match.group(1).replace('**', '').strip()
                if len(text) > 5:
                    report["areas_for_improvement"].append(text)
    
    # 如果没找到，尝试从一般列表中提取
    if not report["areas_for_improvement"]:
        all_items_backup = re.findall(r'(?:^|\n)\s*(?:\d+[.、]|\*)\s*(.{10,80}?)(?:\n|$)', markdown_text, re.MULTILINE)
        keywords_improve = ['建议', '提升', '可以', '需要', '缺少', '不足']
        for item in all_items_backup:
            item = item.strip().replace('**', '')
            if any(kw in item for kw in keywords_improve) and len(report["areas_for_improvement"]) < 5:
                if not item.startswith('#') and '优势' not in item[:20]:
                    report["areas_for_improvement"].append(item[:100])
    
    # 提取求职建议
    job_suggestions = re.findall(r'(?:求职建议|求职.*建议)[:：]?\s*[-–]?\s*(.+)', markdown_text)
    job_search_suggestion = job_suggestions[0] if job_suggestions else "继续提升专业技能，积累更多项目经验。"
    report["suggestions"] = {
        "job_search": job_search_suggestion.strip()
    }
    
    # 提取职业成长建议
    career_suggestions = re.findall(r'(?:职业成长|职业.*建议|成长建议)[:：]?\s*\n((?:(?:(?!###|##|---|🎯|💡).+\n))+)"', markdown_text, re.DOTALL)
    if career_suggestions:
        career_list = re.findall(r'(?:^|\n)\s*(?:\*|[0-9]+\.|、)\s*(.+)', career_suggestions[0])
        report["suggestions"]["career_growth"] = [s.strip() for s in career_list if s.strip()]
    
    if "career_growth" not in report["suggestions"] or not report["suggestions"]["career_growth"]:
        # 从全文中提取职业成长相关建议
        growth_keywords = ['短期', '中期', '长期', '建议']
        all_lines = markdown_text.split('\n')
        growth_suggestions = []
        for line in all_lines:
            line = line.strip()
            if any(kw in line for kw in growth_keywords) and len(line) > 15:
                line = re.sub(r'^\s*[-*]\s*', '', line)
                line = re.sub(r'^\s*[0-9]+\.\s*', '', line)
                growth_suggestions.append(line)
        report["suggestions"]["career_growth"] = growth_suggestions[:3] if growth_suggestions else [
            "持续学习新技术，提升专业能力",
            "积累更多实际项目经验",
            "培养业务理解能力和沟通协作能力"
        ]
    
    # 计算对话统计
    report["conversation_stats"] = {
        "user_message_count": 0,
        "total_user_message_length": 0,
        "meaningful_responses": 0
    }
    
    print(f"[报告解析] Markdown解析完成: 综合评分={report.get('overall_score')}, 优势数量={len(report.get('strengths', []))}, 待提升点数量={len(report.get('areas_for_improvement', []))}")
    
    return report


# ==================== 面试报告生成 API ====================

@app.route('/api/interview/report', methods=['POST'])
def generate_interview_report():
    """生成详细的面试报告，调用FastGPT进行AI分析"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': '请求数据为空'}), 400

        session_id = data.get('sessionId', '')
        messages = data.get('messages', [])
        interview_type = data.get('type', 'text')  # 'text' or 'video'

        if not messages:
            return jsonify({'success': False, 'error': '需要提供对话消息'}), 400

        # 构建报告生成的system prompt（统一JSON格式）
        # 根据面试类型使用不同的提示词风格
        if interview_type == 'video':
            # 真人视频面试：专业严苛风格
            system_content = '''你是一个专业的面试评估师，拥有10年经验的资深技术/HR面试官。根据用户的面试对话记录，生成一份详细的面试评估报告。

【角色设定】
你是一名严格、专业的面试官。在评估时，你会：
- 犀利地指出候选人的不足之处
- 对技术细节和项目经验进行深度拷问
- 给出具有挑战性的评价和建议
- 最终仍会给出建设性的改进方向

【评分体系】
- 岗位适配度 (40%)：经验匹配性、能力契合度、职业认知
- 核心能力表现 (40%)：问题解决、沟通协作、数据结果导向、逻辑表达
- 成长潜力 (20%)：主动意识、学习迭代、抗压适应

**严格要求：**
1. 必须以纯JSON格式输出，不要包含Markdown标记（如```json），也不要输出任何额外的解释性文字。
2. 内容需严格遵守评分要求与风格要求。
3. 量化评分需具体，质性总结需用第二人称，建议需具体可行。
4. **重要：所有内容必须完整输出，不要使用省略号（...）或截断内容，每项建议都要完整呈现。**

**JSON结构规范：**
{
  "quantitative_score": {
    "total_score": Number, // 总分 (0-100)
    "dimension_scores": {
      "job_fit": Number, // 岗位适配度得分 (0-40)
      "core_competency": Number, // 核心能力表现得分 (0-40)
      "growth_potential": Number // 成长潜力得分 (0-20)
    }
  },
  "qualitative_summary": {
    "strengths": "String - 优势提炼。结合具体案例肯定候选人亮点（第二人称）。要犀利但公正。",
    "improvement_areas": "String - 待提升点。尖锐指出可改进方向。用第二人称"你"，具体且不留情面。"
  },
  "actionable_suggestions": {
    "interview_advice": "String - 求职建议。针对面试或入职准备。要具体且具有挑战性。",
    "career_advice": "String - 职业成长建议。从长期发展角度提出。要现实且严苛。"
  }
}

只输出JSON，不要任何其他内容。'''
        else:
            # 文字面试：温和鼓励风格
            system_content = '''你是一个专业的面试评估师，拥有10年经验的资深HR面试官。根据用户的面试对话记录，生成一份详细的面试评估报告。

【角色设定】
你是一名温和、鼓励、建设性的面试官。在评估时，你会：
- 先肯定候选人的亮点
- 温和地指出可以改进的地方
- 给出具体可行的建议
- 帮助候选人建立信心

【评分体系】
- 岗位适配度 (40%)：经验匹配性、能力契合度、职业认知
- 核心能力表现 (40%)：问题解决、沟通协作、数据结果导向、逻辑表达
- 成长潜力 (20%)：主动意识、学习迭代、抗压适应

**严格要求：**
1. 必须以纯JSON格式输出，不要包含Markdown标记（如```json），也不要输出任何额外的解释性文字。
2. 内容需严格遵守评分要求与风格要求。
3. 量化评分需具体，质性总结需用第二人称，建议需具体可行。
4. **重要：所有内容必须完整输出，不要使用省略号（...）或截断内容，每项建议都要完整呈现。**

**JSON结构规范：**
{
  "quantitative_score": {
    "total_score": Number, // 总分 (0-100)
    "dimension_scores": {
      "job_fit": Number, // 岗位适配度得分 (0-40)
      "core_competency": Number, // 核心能力表现得分 (0-40)
      "growth_potential": Number // 成长潜力得分 (0-20)
    }
  },
  "qualitative_summary": {
    "strengths": "String - 优势提炼。结合具体案例肯定候选人亮点（第二人称）。要温暖且真诚。",
    "improvement_areas": "String - 待提升点。温和指出可改进方向。用第二人称"你"，具体且鼓励性。"
  },
  "actionable_suggestions": {
    "interview_advice": "String - 求职建议。针对面试或入职准备。要具体且可行。",
    "career_advice": "String - 职业成长建议。从长期发展角度提出。要温暖且具有指导性。"
  }
}

只输出JSON，不要任何其他内容。'''

        # 将对话历史整理为文本
        conversation_text = ""
        for msg in messages:
            if msg.get('role') == 'user' and msg.get('content') != '结束面试':
                conversation_text += f"【用户回答】{msg.get('content', '')}\n\n"
            elif msg.get('role') == 'assistant':
                conversation_text += f"【面试官问题】{msg.get('content', '')}\n\n"

        user_prompt = f"【面试对话记录】\n{conversation_text}\n\n请根据以上面试对话生成详细的评估报告。"

        # 调用豆包 API 生成报告
        api_url = config.INTERVIEW_DOBAO_URL
        api_key = config.INTERVIEW_DOBAO_API_KEY
        model = config.INTERVIEW_DOBAO_MODEL
        
        print(f"[报告生成] 面试类型: {interview_type}")
        print(f"[报告生成] 对话数量: {len(messages)}")
        print(f"[报告生成] 使用模型: {model}")

        # 构建豆包API请求格式
        doubao_headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        doubao_payload = {
            'model': model,
            'messages': [
                {'role': 'system', 'content': system_content},
                {'role': 'user', 'content': user_prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 4000,
            'stream': False
        }

        response = requests.post(
            api_url,
            json=doubao_payload,
            headers=doubao_headers,
            timeout=120  # 豆包API响应更快
        )
        response.raise_for_status()
        result = response.json()

        ai_content = ''
        if 'choices' in result and len(result['choices']) > 0:
            ai_content = result['choices'][0].get('message', {}).get('content', '')

        # 解析响应
        report_data = None
        raw_markdown = ai_content
        
        if ai_content:
            # 尝试解析 JSON 格式
            try:
                cleaned = ai_content.strip()
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:]
                if cleaned.startswith('```'):
                    cleaned = cleaned[3:]
                if cleaned.endswith('```'):
                    cleaned = cleaned[:-3]
                cleaned = cleaned.strip()
                report_data = json.loads(cleaned)
                print(f"[报告生成] JSON格式解析成功")
                print(f"[报告生成] AI原始数据keys: {list(report_data.keys()) if isinstance(report_data, dict) else type(report_data)}")
            except json.JSONDecodeError:
                print(f"[报告生成] JSON解析失败，尝试从Markdown中提取JSON")
                
                # 尝试从 Markdown 文本中提取 JSON
                # 查找 JSON 对象（以 { 开头，以 } 结尾）
                json_match = re.search(r'\{[\s\S]*"overall_score"[\s\S]*\}', ai_content)
                if json_match:
                    try:
                        json_str = json_match.group(0)
                        report_data = json.loads(json_str)
                        print(f"[报告生成] 从Markdown中成功提取JSON")
                    except json.JSONDecodeError:
                        print(f"[报告生成] 提取的JSON解析失败")
                        report_data = None
                
                # 如果仍未解析成功，尝试解析 Markdown 格式
                if not report_data:
                    print(f"[报告生成] 尝试Markdown格式解析")
                    report_data = parse_markdown_report(ai_content)
                    if not report_data:
                        print(f"[报告生成] Markdown解析也失败，保留原始内容")
                        # 保留原始 Markdown 内容
                        report_data = {
                            "raw_markdown": ai_content,
                            "is_raw_markdown": True
                        }

        # 如果解析失败，返回原始响应
        if not report_data:
            # 生成默认报告
            report_data = generate_fallback_report(messages)
            print(f"[报告生成] 使用降级报告")

        # 计算对话统计
        user_message_count = sum(1 for m in messages if m.get('role') == 'user' and m.get('content') != '结束面试')
        total_user_message_length = sum(len(m.get('content', '')) for m in messages if m.get('role') == 'user')
        meaningful_responses = sum(1 for m in messages if m.get('role') == 'user' and len(m.get('content', '')) > 20)

        # 确保对话统计存在
        if 'conversation_stats' not in report_data:
            report_data['conversation_stats'] = {}
        report_data['conversation_stats']['user_message_count'] = user_message_count
        report_data['conversation_stats']['total_user_message_length'] = total_user_message_length
        report_data['conversation_stats']['meaningful_responses'] = meaningful_responses
        
        # 对报告数据中的文本字段进行图片引用过滤
        def clean_report_fields(data):
            """递归清理报告数据中的图片引用"""
            if isinstance(data, dict):
                return {k: clean_report_fields(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [clean_report_fields(item) for item in data]
            elif isinstance(data, str):
                return clean_image_references(data)
            return data
        
        report_data = clean_report_fields(report_data)
        print(f"[报告生成] clean后数据keys: {list(report_data.keys()) if isinstance(report_data, dict) else type(report_data)}")

        # 统一为蛇形命名格式（将quantitative_score格式转为score_details/strengths等）
        report_data = normalize_report_format(report_data)
        print(f"[报告生成] normalize后数据keys: {list(report_data.keys()) if isinstance(report_data, dict) else type(report_data)}")
        print(f"[报告生成] strengths: {report_data.get('strengths', 'MISSING')}")
        print(f"[报告生成] areas_for_improvement: {report_data.get('areas_for_improvement', 'MISSING')}")
        print(f"[报告生成] suggestions: {report_data.get('suggestions', 'MISSING')}")

        # 返回蛇形命名格式，前端convertApiReportToFrontend函数会转换为驼峰命名
        return jsonify({
            'success': True,
            'report': report_data
        })

    except requests.exceptions.Timeout:
        print(f"[报告生成] API请求超时")
        # 返回降级报告
        fallback_report = generate_fallback_report([])
        fallback_report = normalize_report_format(fallback_report)
        return jsonify({
            'success': True,
            'report': fallback_report
        })
    except Exception as e:
        print(f"[报告生成] 错误: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


def generate_fallback_report(messages):
    """生成降级报告（当API调用失败时使用）"""
    user_message_count = sum(1 for m in messages if m.get('role') == 'user' and m.get('content') != '结束面试')
    total_user_message_length = sum(len(m.get('content', '')) for m in messages if m.get('role') == 'user')
    meaningful_responses = sum(1 for m in messages if m.get('role') == 'user' and len(m.get('content', '')) > 20)

    # 简单计算分数
    if user_message_count == 0:
        overall_score = 30
        score_level = '较差'
    else:
        message_count_score = min(user_message_count * 3, 30)
        message_length_score = min(total_user_message_length / 20, 20)
        meaningful_score = min(meaningful_responses * 10, 50)
        overall_score = message_count_score + message_length_score + meaningful_score
        if overall_score >= 85:
            score_level = '优秀'
        elif overall_score >= 70:
            score_level = '良好'
        elif overall_score >= 60:
            score_level = '及格'
        else:
            score_level = '较差'

    job_fit_score = round(overall_score * 0.4)
    core_ability_score = round(overall_score * 0.4)
    growth_potential_score = round(overall_score * 0.2)

    return {
        "overall_score": overall_score,
        "score_level": score_level,
        "score_details": [
            {
                "dimension": "岗位适配度",
                "weight": "40%",
                "score": f"{job_fit_score}/40",
                "weighted_score": job_fit_score,
                "criteria": "通过交流表现出与岗位需求的基本匹配度" if overall_score >= 70 else "需要更充分展示与岗位相关的能力和经验"
            },
            {
                "dimension": "核心能力表现",
                "weight": "40%",
                "score": f"{core_ability_score}/40",
                "weighted_score": core_ability_score,
                "criteria": "沟通表达能力基本符合岗位要求" if overall_score >= 70 else "需要提升表达能力和展示自己的能力"
            },
            {
                "dimension": "成长潜力",
                "weight": "20%",
                "score": f"{growth_potential_score}/20",
                "weighted_score": growth_potential_score,
                "criteria": "具备一定的学习和成长意愿" if overall_score >= 70 else "需要更积极地展示学习和成长的意愿"
            }
        ],
        "strengths": ["在面试过程中积极参与交流"] if overall_score >= 70 else ["完成了基础的面试流程"],
        "areas_for_improvement": ["可以在回答中提供更多具体的案例和细节"] if overall_score >= 70 else ["回复内容较为简短，建议提供更详细的信息"],
        "suggestions": {
            "job_search": "建议在面试中提供更多具体的工作案例和数据支持。" if overall_score >= 70 else "建议在后续面试中更加积极主动地展示自己。",
            "career_growth": [
                "继续保持积极的学习态度",
                "提升面试中的表达能力和案例展示"
            ] if overall_score >= 70 else [
                "提升面试技巧和沟通能力",
                "面试前进行充分准备"
            ]
        },
        "conversation_stats": {
            "user_message_count": user_message_count,
            "total_user_message_length": total_user_message_length,
            "meaningful_responses": meaningful_responses
        }
    }


# ==================== 岗位采集 API ====================

@app.route('/api/jobs/scrape', methods=['POST'])
def jobs_scrape():
    try:
        data = request.get_json()
        keyword = data.get('keyword', '').strip()
        city = data.get('city', '全国')
        platforms = data.get('platforms', ['shixiseng'])
        max_pages = int(data.get('maxPages', 3))

        # 详细日志：收到的请求参数
        log_info(f"="*60)
        log_info(f"[采集请求] 关键词: {keyword}")
        log_info(f"[采集请求] 城市: {city}")
        log_info(f"[采集请求] 平台: {platforms}")
        log_info(f"[采集请求] 最大页数: {max_pages}")
        log_info(f"="*60)

        if not keyword:
            return jsonify({'success': False, 'error': '请输入搜索关键词'}), 400

        try:
            from backend.scraper.anti_detect.stealth import PLAYWRIGHT_AVAILABLE
        except Exception:
            PLAYWRIGHT_AVAILABLE = False

        if not PLAYWRIGHT_AVAILABLE:
            log_error(f"[采集] Playwright 未安装!")
            return jsonify({
                'success': False,
                'error': 'Playwright 未安装',
                'install_hint': '请运行以下命令安装:\npip install playwright\nplaywright install chromium'
            }), 503

        backend_cfg = get_backend_config()
        db = get_db()
        total_inserted = 0
        results = {}

        # 完整的爬虫映射表
        scraper_map = {
            'shixiseng': lambda: __import__('backend.scraper.shixiseng', fromlist=['ShixisengScraper']).ShixisengScraper(backend_cfg),
            'boss': lambda: __import__('backend.scraper.boss', fromlist=['BossScraper']).BossScraper(backend_cfg),
            'zhilian': lambda: __import__('backend.scraper.zhilian', fromlist=['ZhilianScraper']).ZhilianScraper(backend_cfg),
            'wuyou': lambda: __import__('backend.scraper.wuyou', fromlist=['WuyouScraper']).WuyouScraper(backend_cfg),
            'wyu': lambda: __import__('backend.scraper.wyu', fromlist=['WyuScraper']).WyuScraper(backend_cfg),
            'wyujob': lambda: __import__('backend.scraper.wyujob', fromlist=['WyuJobScraper']).WyuJobScraper(backend_cfg),
            'enterprise': lambda: __import__('backend.scraper.enterprise', fromlist=['EnterpriseScraper']).EnterpriseScraper(backend_cfg),
        }

        log_info(f"[采集] 可用的爬虫: {list(scraper_map.keys())}")

        for platform in platforms:
            log_info(f"-"*40)
            log_info(f"[采集] 正在处理平台: {platform}")
            
            if platform not in scraper_map:
                log_error(f"[采集] 平台 '{platform}' 不在爬虫映射表中!")
                log_error(f"[采集] 跳过此平台")
                results[platform] = {'error': f'平台 {platform} 不支持'}
                continue
                
            try:
                log_info(f"[采集] 正在创建 {platform} 爬虫...")
                scraper = scraper_map[platform]()
                log_info(f"[采集] 爬虫创建成功，开始采集...")
                
                jobs = scraper.scrape(keyword, city, max_pages)
                log_info(f"[采集] 采集完成，获取 {len(jobs)} 条数据")
                
                log_info(f"[采集] 正在插入数据库...")
                inserted = db.insert_jobs(jobs)
                log_info(f"[采集] 数据库插入完成，新增 {inserted} 条")
                
                total_inserted += inserted
                results[platform] = {'found': len(jobs), 'inserted': inserted}
                log_info(f"[{platform}] 采集 {len(jobs)} 条，新增 {inserted} 条")
                
            except RuntimeError as e:
                log_error(f"[{platform}] RuntimeError: {e}")
                import traceback
                log_error(traceback.format_exc())
                results[platform] = {'error': str(e)}
            except Exception as e:
                log_error(f"[{platform}] 采集失败: {e}")
                import traceback
                log_error(traceback.format_exc())
                results[platform] = {'error': str(e)}

        log_info(f"="*60)
        log_info(f"[采集完成] 总计: 获取 {sum(r.get('found', 0) for r in results.values())} 条，新增 {total_inserted} 条")
        log_info(f"="*60)

        return jsonify({
            'success': True,
            'total_inserted': total_inserted,
            'results': results
        })
    except Exception as e:
        log_error(f"采集失败: {e}")
        import traceback
        log_error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/list', methods=['GET'])
def jobs_list():
    try:
        db = get_db()
        filters = {}
        if request.args.get('platform'):
            filters['platform'] = request.args.get('platform')
        if request.args.get('city'):
            filters['city'] = request.args.get('city')
        if request.args.get('keyword'):
            filters['keyword'] = request.args.get('keyword')
        if request.args.get('retained_only') == 'true':
            filters['retained_only'] = True
        jobs = db.query_jobs(filters)
        # Convert skills JSON string to list for frontend
        for job in jobs:
            if isinstance(job.get('skills'), str):
                try:
                    job['skills'] = json.loads(job['skills'])
                except Exception:
                    job['skills'] = []
        return jsonify({'success': True, 'jobs': jobs, 'total': len(jobs)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/retain', methods=['POST'])
def jobs_retain():
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        if not job_id:
            return jsonify({'success': False, 'error': 'job_id 必填'}), 400
        get_db().retain_job(int(job_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/unretain', methods=['POST'])
def jobs_unretain():
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        if not job_id:
            return jsonify({'success': False, 'error': 'job_id 必填'}), 400
        get_db().unretain_job(int(job_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/detail/<int:job_id>', methods=['GET'])
def jobs_detail(job_id):
    try:
        job = get_db().get_job_by_id(job_id)
        if not job:
            return jsonify({'success': False, 'error': '岗位不存在'}), 404
        if isinstance(job.get('skills'), str):
            try:
                job['skills'] = json.loads(job['skills'])
            except Exception:
                job['skills'] = []
        return jsonify({'success': True, 'job': job})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/jobs/clear', methods=['POST'])
def jobs_clear():
    try:
        get_db().hard_clear_jobs()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 简历管理 API ====================

@app.route('/api/resume/upload', methods=['POST'])
def resume_upload():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有文件'}), 400
        f = request.files['file']
        if not f.filename or not allowed_file(f.filename):
            return jsonify({'success': False, 'error': '不支持的文件格式，请上传 PDF/DOC/DOCX'}), 400

        # 强制校验：头像为必填项
        if 'avatar' not in request.files or not request.files['avatar'].filename:
            return jsonify({
                'success': False,
                'error': '头像照片为必填项，请先选择头像照片后再上传简历',
                'require_avatar': True
            }), 400
        avatar_file = request.files['avatar']
        if not allowed_avatar_file(avatar_file.filename):
            return jsonify({'success': False, 'error': '不支持的图片格式，请使用 JPG/PNG/GIF/WebP 格式'}), 400

        # Save file
        from werkzeug.utils import secure_filename
        filename = secure_filename(f.filename)
        ext = f.filename.rsplit('.', 1)[-1].lower()
        # Always use timestamp prefix to avoid problematic filenames (especially those starting with '-')
        filename = f"resume_{int(time.time())}.{ext}"

        save_path = config.UPLOAD_FOLDER / filename
        # Avoid name collision
        counter = 1
        stem = save_path.stem
        while save_path.exists():
            save_path = config.UPLOAD_FOLDER / f"{stem}_{counter}{save_path.suffix}"
            counter += 1
        f.save(str(save_path))

        db = get_db()
        resume_id = db.upsert_resume({
            'file_name': filename,
            'file_path': str(save_path),
            'file_type': save_path.suffix.lstrip('.').lower(),
            'is_primary': request.form.get('is_primary', '0') == '1',
        })

        # Handle avatar upload (必填，已在上方校验)
        avatar_path = None
        avatar_file = request.files['avatar']
        logger.info(f"[上传] 收到头像文件: {avatar_file.filename}（必填项）")
        avatar_ext = avatar_file.filename.rsplit('.', 1)[-1].lower()
        avatar_filename = f"avatar_{int(time.time())}.{avatar_ext}"
        avatar_save_path = config.UPLOAD_FOLDER / avatar_filename
        avatar_file.save(str(avatar_save_path))
        # 保存相对路径，用于浏览器访问（通过 /uploads/<filename> 路由）
        avatar_path = f"/uploads/{avatar_filename}"
        logger.info(f"[上传] 保存头像(必填): {avatar_path}")
        db.update_resume_avatar(resume_id, avatar_path)
        logger.info(f"[上传] 头像已保存到数据库")

        # Auto-parse if Doubao configured
        parse_requested = request.form.get('parse', '1') == '1'
        parsed_data = None
        if parse_requested:
            try:
                backend_cfg = get_backend_config()
                from backend.resume.parser import ResumeParser
                parser = ResumeParser(backend_cfg)
                parsed_data = parser.parse(save_path)
                logger.info(f"[简历解析] 解析结果字段: {list(parsed_data.keys()) if parsed_data else 'None'}")
                parsed_data_json = json.dumps(parsed_data, ensure_ascii=False)
                db.update_resume_parsed_data(resume_id, parsed_data_json)
                # If avatar was uploaded, restore it in parsed_data for PDF generation
                if avatar_path:
                    try:
                        parsed_data['avatar'] = avatar_path
                        parsed_data_json = json.dumps(parsed_data, ensure_ascii=False)
                        db.update_resume_parsed_data(resume_id, parsed_data_json)
                    except Exception:
                        pass
            except Exception as e:
                log_error(f"简历解析失败: {e}")

        return jsonify({
            'success': True,
            'resume_id': resume_id,
            'file_name': filename,
            'parsed': parsed_data is not None,
            'parsed_data': parsed_data,
            'avatar_uploaded': avatar_path is not None,
        })
    except Exception as e:
        log_error(f"上传失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def allowed_avatar_file(filename: str) -> bool:
    """Check if the avatar file extension is allowed"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


@app.route('/api/resume/avatar/upload', methods=['POST'])
def resume_avatar_upload():
    """为已有简历上传头像"""
    try:
        logger.info(f"[头像] 收到上传请求, files={list(request.files.keys())}, form={list(request.form.keys())}")
        
        if 'avatar' not in request.files:
            logger.warning("[头像] 没有avatar文件")
            return jsonify({'success': False, 'error': '没有头像文件'}), 400
        if 'resume_id' not in request.form:
            logger.warning("[头像] 没有resume_id")
            return jsonify({'success': False, 'error': 'resume_id 必填'}), 400

        avatar_file = request.files['avatar']
        resume_id = int(request.form['resume_id'])
        logger.info(f"[头像] 文件名={avatar_file.filename}, resume_id={resume_id}")

        if not avatar_file.filename or not allowed_avatar_file(avatar_file.filename):
            logger.warning(f"[头像] 文件格式不支持: {avatar_file.filename}")
            return jsonify({'success': False, 'error': '不支持的文件格式'}), 400

        avatar_ext = avatar_file.filename.rsplit('.', 1)[-1].lower()
        avatar_filename = f"avatar_{int(time.time())}.{avatar_ext}"
        avatar_save_path = config.UPLOAD_FOLDER / avatar_filename
        avatar_file.save(str(avatar_save_path))
        # 保存相对路径，用于浏览器访问（通过 /uploads/<filename> 路由）
        avatar_path = f"/uploads/{avatar_filename}"
        logger.info(f"[头像] 文件保存成功: {avatar_path}")

        db = get_db()
        db.update_resume_avatar(resume_id, avatar_path)
        logger.info(f"[头像] 数据库更新成功，简历 {resume_id} 的头像: {avatar_path}")

        return jsonify({'success': True, 'avatar_path': avatar_path})
    except Exception as e:
        import traceback
        logger.error(f"[头像] 上传失败: {e}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/resume/list', methods=['GET'])
def resume_list():
    try:
        resumes = get_db().get_all_resumes()
        for r in resumes:
            if isinstance(r.get('parsed_data'), str) and r['parsed_data']:
                try:
                    r['parsed_data'] = json.loads(r['parsed_data'])
                except Exception:
                    r['parsed_data'] = None
        return jsonify({'success': True, 'resumes': resumes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/resume/set-primary', methods=['POST'])
def resume_set_primary():
    try:
        data = request.get_json()
        resume_id = data.get('resume_id')
        if not resume_id:
            return jsonify({'success': False, 'error': 'resume_id 必填'}), 400
        get_db().set_primary_resume(int(resume_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/resume/delete', methods=['POST'])
def resume_delete():
    try:
        data = request.get_json()
        resume_id = data.get('resume_id')
        if not resume_id:
            return jsonify({'success': False, 'error': 'resume_id 必填'}), 400
        get_db().delete_resume(int(resume_id))
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/resume/get', methods=['GET'])
def resume_get():
    try:
        db = get_db()
        resume_id = request.args.get('id')
        if resume_id:
            resumes = db.get_all_resumes()
            resume = next((r for r in resumes if str(r['id']) == str(resume_id)), None)
        else:
            resume = db.get_primary_resume()
        if not resume:
            return jsonify({'success': False, 'error': '简历不存在'}), 404
        if isinstance(resume.get('parsed_data'), str) and resume['parsed_data']:
            try:
                resume['parsed_data'] = json.loads(resume['parsed_data'])
            except Exception:
                resume['parsed_data'] = None
        return jsonify({'success': True, 'resume': resume})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 岗位匹配 API ====================

@app.route('/api/match/start', methods=['POST'])
def match_start():
    try:
        data = request.get_json() or {}
        resume_id = data.get('resume_id')
        db = get_db()

        if resume_id:
            resumes = db.get_all_resumes()
            resume = next((r for r in resumes if str(r['id']) == str(resume_id)), None)
        else:
            resume = db.get_primary_resume()

        if not resume:
            return jsonify({'success': False, 'error': '未找到简历，请先上传简历'}), 400

        parsed_data = resume.get('parsed_data')
        if isinstance(parsed_data, str) and parsed_data:
            try:
                parsed_data = json.loads(parsed_data)
            except Exception:
                parsed_data = {}
        if not parsed_data:
            return jsonify({'success': False, 'error': '简历未解析，请先解析简历'}), 400

        jobs = db.query_jobs({'retained_only': True})
        if not jobs:
            return jsonify({'success': False, 'error': '没有已留存的岗位，请先在岗位采集中留存感兴趣的岗位'}), 400

        # Convert skills string to list
        for job in jobs:
            if isinstance(job.get('skills'), str):
                try:
                    job['skills'] = json.loads(job['skills'])
                except Exception:
                    job['skills'] = []

        backend_cfg = get_backend_config()
        from backend.processor.matcher import AIJobMatcher
        matcher = AIJobMatcher(backend_cfg)
        matched = matcher.batch_match(parsed_data, jobs)

        # Persist match results to database
        resume_db_id = resume.get('id')
        if resume_db_id:
            for m in matched:
                try:
                    # Use m['id'] (database primary key) not m['job_id'] (platform job ID)
                    get_db().upsert_match_result({
                        'resume_id': resume_db_id,
                        'job_id': m['id'],  # Database primary key
                        'match_score': m.get('match_score', 0),
                        'skill_score': m.get('skill_score', 0),
                        'fit_score': m.get('fit_score', 0),
                        'salary_score': m.get('salary_score', 0),
                        'matched_skills': m.get('matched_skills', []),
                        'missing_skills': m.get('missing_skills', []),
                        'ai_analysis': m.get('ai_analysis', ''),
                        'ai_strengths': m.get('ai_strengths', ''),
                        'ai_suggestions': m.get('ai_suggestions', ''),
                        'jd_missing': m.get('jd_missing', False),
                    })
                except Exception as me:
                    log_error(f"保存匹配结果失败: {me}")

        return jsonify({'success': True, 'results': matched, 'total': len(matched)})
    except Exception as e:
        log_error(f"匹配失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 简历优化 API ====================

@app.route('/api/resume/optimize', methods=['POST'])
def resume_optimize():
    try:
        data = request.get_json()
        resume_id = data.get('resume_id')
        job_id = data.get('job_id')
        options = data.get('options', {})

        if not resume_id or not job_id:
            return jsonify({'success': False, 'error': 'resume_id 和 job_id 必填'}), 400

        db = get_db()
        resumes = db.get_all_resumes()
        resume = next((r for r in resumes if str(r['id']) == str(resume_id)), None)
        job = db.get_job_by_id(int(job_id))

        if not resume:
            return jsonify({'success': False, 'error': '简历不存在'}), 404
        if not job:
            return jsonify({'success': False, 'error': '岗位不存在'}), 404

        parsed_data = resume.get('parsed_data')
        if isinstance(parsed_data, str) and parsed_data:
            try:
                parsed_data = json.loads(parsed_data)
            except Exception:
                parsed_data = {}
        if not parsed_data:
            return jsonify({'success': False, 'error': '简历未解析'}), 400
        
        # 将数据库中的头像路径合并到 parsed_data
        logger.info(f"[简历优化] resume avatar_path: {resume.get('avatar_path')}")
        logger.info(f"[简历优化] resume keys: {list(resume.keys())}")
        if resume.get('avatar_path'):
            parsed_data['avatar'] = resume['avatar_path']
            logger.info(f"[简历优化] 设置头像路径: {resume['avatar_path']}")
            logger.info(f"[简历优化] parsed_data avatar: {parsed_data.get('avatar')}")

        if isinstance(job.get('skills'), str):
            try:
                job['skills'] = json.loads(job['skills'])
            except Exception:
                job['skills'] = []

        backend_cfg = get_backend_config()
        from backend.resume.tailor import ResumeTailor
        tailor = ResumeTailor(backend_cfg)
        result = tailor.tailor(parsed_data, job, options=options)

        if result['status'] == 'success':
            tailored_id = db.insert_tailored_resume({
                'base_resume_id': int(resume_id),
                'job_id': int(job_id),
                'file_name': result['file_name'],
                'file_path': result['pdf_path'],
                'status': 'ready',
            })
            return jsonify({
                'success': True,
                'tailored_id': tailored_id,
                'file_name': result['file_name'],
                'pdf_path': result['pdf_path'],
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', '生成失败')}), 500
    except Exception as e:
        log_error(f"简历优化失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/resume/tailored/list', methods=['GET'])
def tailored_list():
    try:
        tailored = get_db().get_tailored_resumes()
        return jsonify({'success': True, 'resumes': tailored})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/resume/tailored/download/<int:tailored_id>', methods=['GET'])
def tailored_download(tailored_id):
    try:
        db = get_db()
        resumes = db.get_tailored_resumes(limit=1000)
        resume = next((r for r in resumes if r['id'] == tailored_id), None)
        if not resume:
            return jsonify({'error': '文件不存在'}), 404
        file_path = Path(resume['file_path'])
        if not file_path.exists():
            return jsonify({'error': '文件已被删除'}), 404
        return send_file(str(file_path), as_attachment=True,
                         download_name=resume['file_name'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 自动投递 API ====================

@app.route('/api/apply/browser', methods=['POST'])
def apply_browser():
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        if not job_id:
            return jsonify({'success': False, 'error': 'job_id 必填'}), 400

        try:
            from backend.applicator.browser import BrowserApplicator, SELENIUM_AVAILABLE
        except Exception:
            SELENIUM_AVAILABLE = False

        if not SELENIUM_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'Selenium 未安装',
                'install_hint': '请运行: pip install selenium undetected-chromedriver\n并安装 Chrome 浏览器'
            }), 503

        job = get_db().get_job_by_id(int(job_id))
        if not job:
            return jsonify({'success': False, 'error': '岗位不存在'}), 404

        backend_cfg = get_backend_config()
        from backend.applicator.browser import BrowserApplicator
        with BrowserApplicator(backend_cfg) as applicator:
            result = applicator.login_and_apply(job)

        if result.get('success'):
            get_db().insert_application({
                'job_id': int(job_id),
                'method': 'browser',
                'status': 'submitted',
            })

        return jsonify(result)
    except Exception as e:
        log_error(f"浏览器投递失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/apply/shixiseng-batch', methods=['POST'])
def apply_shixiseng_batch():
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        if not urls:
            return jsonify({'success': False, 'error': '未提供投递链接'}), 400

        # 检查 Playwright 可用性
        playwright_available = False
        try:
            from backend.applicator.shixiseng_apply import ShixisengAutoApply, ShixisengApplyConfig
            playwright_available = True
        except ImportError as e:
            log_error(f"导入失败: {e}")

        if not playwright_available:
            return jsonify({
                'success': False,
                'error': 'Playwright 未安装',
                'install_hint': '请运行:\npip install playwright\nplaywright install chromium'
            }), 503

        delay_min = int(data.get('delay_min', 10))
        delay_max = int(data.get('delay_max', 30))
        
        # 使用新的配置类
        config = ShixisengApplyConfig(
            delay_min=delay_min,
            delay_max=delay_max,
            headless=False
        )
        applier = ShixisengAutoApply(config)
        results = applier.batch_apply(urls)

        # Record all application results
        db = get_db()
        for r in results:
            status = r.get('status', '')
            app_status = 'submitted' if status == 'success' else 'failed'
            error_msg = r.get('message', '') if status != 'success' else ''
            db.insert_application({
                'job_id': None,  # 外部链接投递，不关联具体岗位
                'method': 'shixiseng_batch',
                'status': app_status,
                'error_message': error_msg,
                'job_url': r.get('url', ''),
                'job_title': r.get('job_title', '实习僧岗位'),
            })

        return jsonify({'success': True, 'results': results, 'total': len(results)})
    except Exception as e:
        log_error(f"实习僧批量投递失败: {e}")
        import traceback
        log_error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/apply/email', methods=['POST'])
def apply_email():
    try:
        data = request.get_json()
        job_id = data.get('job_id')
        tailored_resume_id = data.get('tailored_resume_id')
        to_email = data.get('to_email', '')
        applicant_name = data.get('applicant_name', '')
        custom_intro = data.get('custom_intro', '')

        if not job_id:
            return jsonify({'success': False, 'error': 'job_id 必填'}), 400

        db = get_db()
        job = db.get_job_by_id(int(job_id))
        if not job:
            return jsonify({'success': False, 'error': '岗位不存在'}), 404

        # Get resume file
        resume_path = None
        if tailored_resume_id:
            tailored_list = db.get_tailored_resumes(limit=1000)
            tr = next((r for r in tailored_list if r['id'] == int(tailored_resume_id)), None)
            if tr:
                resume_path = Path(tr['file_path'])
        if not resume_path or not resume_path.exists():
            primary = db.get_primary_resume()
            if primary:
                resume_path = Path(primary['file_path'])
        if not resume_path or not resume_path.exists():
            return jsonify({'success': False, 'error': '未找到简历文件'}), 400

        backend_cfg = get_backend_config()
        try:
            from backend.applicator.email_sender import EmailApplicator
            applicator = EmailApplicator(backend_cfg)
        except ValueError as e:
            return jsonify({'success': False, 'error': str(e),
                           'config_hint': '请在页面设置中配置 SMTP 邮箱信息'}), 400

        if isinstance(job.get('skills'), str):
            try:
                job['skills'] = json.loads(job['skills'])
            except Exception:
                job['skills'] = []

        result = applicator.apply(
            job=job,
            resume_path=resume_path,
            applicant_name=applicant_name,
            custom_intro=custom_intro,
            to_email=to_email or None,
        )

        # 统一返回格式
        if result.get('success'):
            db.insert_application({
                'job_id': int(job_id),
                'tailored_resume_id': int(tailored_resume_id) if tailored_resume_id else None,
                'method': 'email',
                'status': 'submitted',
            })
            return jsonify({'success': True, 'message': result.get('message', '投递成功')})
        else:
            return jsonify({'success': False, 'error': result.get('error', '投递失败')})
    except Exception as e:
        log_error(f"邮件投递失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/apply/records', methods=['GET'])
def apply_records():
    try:
        limit = int(request.args.get('limit', 100))
        records = get_db().get_applications(limit=limit)
        return jsonify({'success': True, 'records': records})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 配置管理 API ====================

@app.route('/api/config/update', methods=['POST'])
def config_update():
    """更新 .env 文件中的豆包配置，并热更新后端 config"""
    try:
        data = request.get_json()
        env_path = Path('.env')

        lines = []
        if env_path.exists():
            with open(env_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

        updates = {}
        if data.get('doubao_api_key'):
            updates['DOUBAO_API_KEY'] = data['doubao_api_key']
        if data.get('doubao_model'):
            updates['DOUBAO_MODEL'] = data['doubao_model']
        if data.get('smtp_host'):
            updates['SMTP_HOST'] = data['smtp_host']
        if data.get('smtp_port'):
            updates['SMTP_PORT'] = str(data['smtp_port'])
        if data.get('smtp_email'):
            updates['SMTP_EMAIL'] = data['smtp_email']
        if data.get('smtp_password'):
            updates['SMTP_PASSWORD'] = data['smtp_password']

        # Update existing or append new
        updated_keys = set()
        new_lines = []
        for line in lines:
            key = line.split('=')[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
            else:
                new_lines.append(line)

        for key, val in updates.items():
            if key not in updated_keys:
                new_lines.append(f"{key}={val}\n")

        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

        # Hot-reload backend config
        global _backend_config
        _backend_config = None

        return jsonify({'success': True, 'message': '配置已更新'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/test-doubao', methods=['POST'])
def config_test_doubao():
    """测试豆包 API 连通性"""
    try:
        data = request.get_json() or {}
        api_key = data.get('api_key') or os.getenv('DOUBAO_API_KEY', '')
        model = data.get('model') or os.getenv('DOUBAO_MODEL', 'ep-20260329183523-7ns5h')
        from backend.utils.doubao_client import DoubaoClient
        client = DoubaoClient(api_key=api_key, model=model)
        response = client.chat(
            messages=[{"role": "user", "content": "你好，请回复「OK」"}],
            max_tokens=10, temperature=0.1,
        )
        return jsonify({'success': True, 'response': response})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config/get', methods=['GET'])
def config_get():
    """获取当前公开配置"""
    backend_cfg = get_backend_config()
    key = backend_cfg.doubao_api_key
    masked_key = (key[:8] + '****' + key[-4:]) if len(key) > 12 else '未配置'
    return jsonify({
        'success': True,
        'doubao_model': backend_cfg.doubao_model,
        'doubao_api_key_masked': masked_key,
        'smtp_host': backend_cfg.smtp_host,
        'smtp_port': backend_cfg.smtp_port,
        'smtp_email': backend_cfg.smtp_email,
        'smtp_configured': bool(backend_cfg.smtp_email and backend_cfg.smtp_password),
    })

# ==================== 岗位（带分数）API ====================

@app.route('/api/jobs/retained-with-scores', methods=['GET'])
def jobs_retained_with_scores():
    try:
        db = get_db()
        resume_id = request.args.get('resume_id')
        if resume_id:
            resume_id = int(resume_id)
        else:
            resume = db.get_primary_resume()
            resume_id = resume['id'] if resume else 0
        jobs = db.get_retained_jobs_with_scores(resume_id)
        return jsonify({'success': True, 'jobs': jobs, 'total': len(jobs), 'resume_id': resume_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 数据统计 API ====================

@app.route('/api/stats/overview', methods=['GET'])
def stats_overview():
    try:
        data = get_db().get_stats_overview()
        return jsonify({'success': True, **data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats/trends', methods=['GET'])
def stats_trends():
    try:
        days = int(request.args.get('days', 7))
        data = get_db().get_stats_trends(days=days)
        return jsonify({'success': True, 'trends': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats/platform', methods=['GET'])
def stats_platform():
    try:
        data = get_db().get_stats_platform_distribution()
        return jsonify({'success': True, 'platforms': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats/applications', methods=['GET'])
def stats_applications():
    try:
        data = get_db().get_stats_application_status()
        return jsonify({'success': True, 'statuses': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 健康检查 ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'port': config.PORT,
        'interview_api': {
            'configured': bool(config.INTERVIEW_DOBAO_API_KEY),
            'provider': 'doubao'
        },
        'version': '2.0.0 (Python)'
    })

# ==================== 错误处理 ====================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': '页面不存在', 'path': request.path}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': '服务器内部错误'}), 500

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': '方法不允许'}), 405

# ==================== 启动服务器 ====================

if __name__ == '__main__':
    import sys
    # 兼容 Windows GBK 终端
    enc = sys.stdout.encoding or 'utf-8'
    def p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode(enc, errors='replace').decode(enc))
    p("\n" + "="*60)
    p(">>> Zhi Neng Zhi Ye Fa Zhan Zhu Shou v2.0")
    p("="*60)
    p(f"\n  URL:  http://localhost:{config.PORT}")
    p(f"  Interview API: 豆包API (Doubao)")
    p(f"  Interview API Key: {'OK' if config.INTERVIEW_DOBAO_API_KEY else 'NOT SET'}")
    p(f"\n  Pages:")
    p(f"    Home:     http://localhost:{config.PORT}")
    p(f"    Jobs:     http://localhost:{config.PORT}/job_scraper.html")
    p(f"    Resume:   http://localhost:{config.PORT}/resume_manage.html")
    p(f"    Match:    http://localhost:{config.PORT}/job_match.html")
    p(f"    Optimize: http://localhost:{config.PORT}/resume_optimize.html")
    p(f"    Apply:    http://localhost:{config.PORT}/auto_apply.html")
    p(f"    Interview:http://localhost:{config.PORT}/interview_coach.html")
    p(f"    Settings: http://localhost:{config.PORT}/settings.html")
    p("\n" + "="*60 + "\n")
    
    # 根据环境变量决定是否启用调试模式
    debug_mode = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=config.PORT, debug=debug_mode)
