"""简历解析器 — 支持 PDF/DOCX，调用豆包 API"""
import json
import re
from pathlib import Path
from typing import Optional

from backend.core.config import Config
from backend.core.exceptions import ResumeParseError
from backend.utils.logger import logger


def _extract_text_pdf(file_path: Path) -> str:
    try:
        import PyPDF2
        parts = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception as e:
        raise ResumeParseError(str(file_path), f"PDF 读取失败: {e}")


def _extract_text_docx(file_path: Path) -> str:
    """从 DOCX 文件提取文本（优先使用 XML 直接提取，提高兼容性）"""
    try:
        import zipfile
        from xml.etree import ElementTree as ET
        
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        texts = []
        
        with zipfile.ZipFile(str(file_path)) as z:
            try:
                doc = ET.parse(z.open('word/document.xml'))
                root = doc.getroot()
                for t in root.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                    if t.text:
                        texts.append(t.text)
            except KeyError:
                pass  # 文件可能没有 document.xml
            
            # 也检查页眉页脚等
            for name in z.namelist():
                if name.startswith('word/header') or name.startswith('word/footer'):
                    try:
                        doc = ET.parse(z.open(name))
                        for t in doc.getroot().iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
                            if t.text:
                                texts.append(t.text)
                    except Exception:
                        pass
        
        result = ''.join(texts)
        if result.strip():
            return result
            
    except Exception as e:
        pass  # 回退到 python-docx
    
    # 回退：尝试使用 python-docx
    try:
        from docx import Document
        doc = Document(str(file_path))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        raise ResumeParseError(str(file_path), f"DOCX 读取失败: {e}")


def extract_raw_text(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return _extract_text_pdf(file_path)
    if ext in (".docx", ".doc"):
        return _extract_text_docx(file_path)
    raise ResumeParseError(str(file_path), f"不支持的格式: {ext}")


_PARSE_SYSTEM = """\
你是专业简历解析助手。请将简历文本解析为以下 JSON 结构，只输出合法 JSON，不含任何说明或代码块。
字段：
- name: 姓名
- phone: 手机号（可空）
- email: 邮箱（可空）
- wechat: 微信号（可空）
- job_intention: 求职意向（可空）
- age: 年龄（可空）
- gender: 性别（可空）
- political_status: 政治面貌（可空）
- native_place: 籍贯（可空）
- education: 列表，每项含 school/degree/major/start/end
- skills: 技能字符串数组
- work_experience: 列表，每项含 company/position/start/end/description
- campus_experience: 校园经历列表，每项含 name（组织名）/position（职位）/start/end/description（可空）
- project_experience: 列表，每项含 name/role（职位角色，如"项目负责人"、"开发成员"等）/start/end/description/duties
- certificates: 证书列表（可空）
- self_intro: 自我评价（可空）"""


def _try_fix_json(raw: str) -> dict:
    """尝试修复被截断的JSON"""
    import json
    
    # 尝试直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    
    # 尝试补全截断的字符串值（引号未闭合）
    try:
        # 找到最后一个完整的字段（逗号或换行后面）
        lines = raw.split('\n')
        fixed_lines = []
        for line in lines:
            stripped = line.rstrip()
            # 如果行以逗号结尾或只有单个字段名，是完整的
            if stripped.endswith(',') or (':' in stripped and stripped.count(':') == 1 and stripped.endswith('"')):
                fixed_lines.append(line)
            elif stripped.endswith('"') or stripped.endswith(']') or stripped.endswith('}'):
                fixed_lines.append(line)
            else:
                # 截断的行，尝试闭合
                if '"' in stripped and stripped.count('"') % 2 == 1:
                    fixed_lines.append(stripped + '"')
                else:
                    fixed_lines.append(stripped)
        
        # 尝试闭合JSON
        fixed = '\n'.join(fixed_lines)
        for suffix in ['"]', '"}', '"]}', '"}]', '}]', '}]}', '}]}]', '}]}}']:
            try:
                return json.loads(fixed + suffix)
            except:
                pass
    except Exception:
        pass
    
    return None


def _parse_with_doubao(raw_text: str, config: Config) -> dict:
    client = config.make_doubao_client()
    try:
        result = client.chat_json(
            messages=[{"role": "user", "content": raw_text}],
            system=_PARSE_SYSTEM,
            max_tokens=4096,
            temperature=0.1,
        )
        if not result or not isinstance(result, dict):
            raise ResumeParseError("doubao", f"豆包API返回空结果或非字典: {type(result)}")
        logger.info(f"豆包API返回字段: {list(result.keys())}")
        return result
    except ValueError as e:
        # 尝试修复被截断的JSON
        logger.warning(f"[doubao] JSON解析失败，尝试修复: {e}")
        try:
            # 获取原始响应内容
            raw_response = client.chat(
                messages=[{"role": "user", "content": raw_text}],
                system=_PARSE_SYSTEM,
                max_tokens=4096,
                temperature=0.1,
            ).strip()
            if raw_response.startswith("```"):
                import re
                raw_response = re.sub(r"```(?:json)?", "", raw_response).strip().rstrip("```").strip()
            
            fixed = _try_fix_json(raw_response)
            if fixed:
                logger.info(f"[doubao] JSON修复成功")
                return fixed
        except Exception as e2:
            logger.error(f"[doubao] JSON修复失败: {e2}")
        raise ResumeParseError("doubao", f"豆包API返回非法JSON: {e}")
    except RuntimeError as e:
        raise ResumeParseError("doubao", f"豆包API调用失败: {e}")


class ResumeParser:
    def __init__(self, config: Config):
        self.config = config

    def parse(self, file_path: Path) -> dict:
        file_path = Path(file_path)
        if not file_path.exists():
            raise ResumeParseError(str(file_path), "文件不存在")
        logger.info(f"开始解析简历: {file_path.name}")
        raw_text = extract_raw_text(file_path)
        if not raw_text.strip():
            raise ResumeParseError(str(file_path), "文件内容为空")
        parsed = _parse_with_doubao(raw_text, self.config)
        parsed["_raw_text"] = raw_text
        parsed.setdefault("name", file_path.stem)
        logger.info(f"解析完成: {parsed.get('name')}")
        return parsed

    def parse_to_json(self, file_path: Path, save_path: Optional[Path] = None) -> dict:
        result = self.parse(file_path)
        if save_path:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        return result
