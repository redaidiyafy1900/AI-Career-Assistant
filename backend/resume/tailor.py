import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, List, Any

from backend.core.config import Config, TAILORED_DIR
from backend.utils.logger import logger

# ===================== 全局配置 =====================
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame, FrameBreak,
        Paragraph, Spacer, Table, TableStyle, NextPageTemplate, Image
    )
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

if REPORTLAB_AVAILABLE:
    COLOR_MAIN = colors.HexColor("#1E40AF")
    COLOR_LIGHT = colors.HexColor("#F0F7FF")
    COLOR_GRAY_LIGHT = colors.HexColor("#F5F7FA")
    COLOR_BORDER = colors.HexColor("#E5E9F2")
    COLOR_TEXT = colors.HexColor("#1D2129")
    COLOR_TEXT_LIGHT = colors.HexColor("#64748B")

PAGE_SIZE = A4
PAGE_W, PAGE_H = A4
MARGIN = 12 * mm
LEFT_COL_WIDTH = 65 * mm
RIGHT_COL_WIDTH = PAGE_W - 2 * MARGIN - LEFT_COL_WIDTH - 5 * mm
COL_SPACING = 5 * mm
MODULE_PADDING = 6 * mm
BORDER_WIDTH = 0.5
AVATAR_SIZE = 28 * mm  # 稍微缩小头像尺寸以适应布局
AVATAR_TOP_MARGIN = 8 * mm  # 头像顶部间距
MAX_SELF_INTRO_LENGTH = 300


# ===================== 工具函数 =====================
def safe_str(value: Any) -> str:
    if value is None or str(value).strip().lower() in ("none", "", "无"):
        return ""
    return str(value).strip()


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def simplify_job_title(job_title: str) -> str:
    """简化岗位名称用于文件名，保留核心关键词"""
    title = safe_str(job_title)
    # 只移除括号内容及特殊字符
    title = re.sub(r"[\(\（][^\)\）]*[\)\）]", "", title)
    # 只移除会影响文件名可读性的词，保留"工程师"、"专员"等核心词
    remove_words = ["全职", "兼职", "社会招聘", "校园招聘", "招聘"]
    for word in remove_words:
        title = title.replace(word, "")
    title = re.sub(r"\s+", " ", title).strip()
    # 限制长度，避免文件名过长
    if len(title) > 20:
        title = title[:20]
    return title if title else "求职岗位"


def get_contact_info(fields: Dict) -> str:
    phone = safe_str(fields.get("phone", "")).replace(" ", "")
    if phone:
        return phone[:11]
    wechat = safe_str(fields.get("wechat", ""))
    if wechat:
        return wechat
    email = safe_str(fields.get("email", ""))
    if email:
        return email.split("@")[0]
    return "无联系方式"


def get_all_user_fields(resume_data: Dict) -> Dict:
    avatar = (
        safe_str(resume_data.get("avatar", ""))
        or safe_str(resume_data.get("photo_path", ""))
    )
    return {
        "name": safe_str(resume_data.get("name", "求职候选人")),
        "job_intention": safe_str(resume_data.get("job_intention", "")),
        "age": safe_str(resume_data.get("age", "")),
        "gender": safe_str(resume_data.get("gender", "")),
        "political_status": safe_str(resume_data.get("political_status", "")),
        "native_place": safe_str(resume_data.get("native_place", "")),
        "phone": safe_str(resume_data.get("phone", "")),
        "email": safe_str(resume_data.get("email", "")),
        "wechat": safe_str(resume_data.get("wechat", "")),
        "avatar": avatar,
        "certificates": safe_list(resume_data.get("certificates", [])),
        "education": safe_list(resume_data.get("education", [])),
        "work_experience": safe_list(resume_data.get("work_experience", [])),
        "campus_experience": safe_list(resume_data.get("campus_experience", [])),
        "project_experience": safe_list(resume_data.get("project_experience", [])),
        "skills": safe_list(resume_data.get("skills", [])),
        "self_intro": safe_str(resume_data.get("self_intro", "")),
    }


# ===================== 字体注册 =====================
def register_font() -> str:
    """注册中文字体，优先使用系统已安装的字体（标点支持好的优先）"""
    import os
    
    # 字体搜索路径（按优先级排序，标点支持好的在前）
    font_paths = []
    
    # Windows 字体路径
    if os.path.exists(r"C:\Windows\Fonts"):
        font_paths.extend([
            r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑（优先，标点支持好）
            r"C:\Windows\Fonts\msyhbd.ttc",     # 微软雅黑粗体
            r"C:\Windows\Fonts\simhei.ttf",     # 黑体
            r"C:\Windows\Fonts\STSONG.TTF",     # 宋体
            r"C:\Windows\Fonts\SIMSUN.TTC",     # 宋体 (SIMSUN.ttc)
            r"C:\Windows\Fonts\simsun.ttc",     # 宋体
            r"C:\Windows\Fonts\STKAITI.TTF",    # 楷体
            r"C:\Windows\Fonts\SIMKAI.TTF",     # 楷体
            r"C:\Windows\Fonts\simkai.ttf",      # 楷体
        ])
    
    # Linux 字体路径
    font_paths.extend([
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ])
    
    # macOS 字体路径
    font_paths.extend([
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ])
    
    # 尝试注册每个字体
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                # 使用唯一字体名称避免冲突
                base_name = os.path.splitext(os.path.basename(font_path))[0]
                font_name = f"CN_{base_name}"
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                logger.info(f"字体注册成功: {font_path}")
                return font_name
            except Exception as e:
                logger.warning(f"字体注册失败 {font_path}: {e}")
                continue
    
    # 如果都失败了，尝试使用内置的Helvetica（不支持中文）
    logger.error("所有中文字体注册失败，PDF中文将无法正确显示")
    return "Helvetica"


# 全局注册字体（避免每次调用重复注册）
if REPORTLAB_AVAILABLE:
    FONT_NAME = register_font()
else:
    FONT_NAME = "Helvetica"


# ===================== 样式定义 =====================
def get_styles() -> Dict[str, "ParagraphStyle"]:
    return {
        "left_name": ParagraphStyle(
            "left_name", fontName=FONT_NAME, fontSize=16, leading=22,
            textColor=COLOR_MAIN, alignment=0
        ),
        "left_job": ParagraphStyle(
            "left_job", fontName=FONT_NAME, fontSize=10, leading=14,
            textColor=COLOR_TEXT, alignment=0
        ),
        "left_title": ParagraphStyle(
            "left_title", fontName=FONT_NAME, fontSize=10, leading=14,
            textColor=COLOR_MAIN, alignment=1
        ),
        "left_content": ParagraphStyle(
            "left_content", fontName=FONT_NAME, fontSize=9, leading=12,
            textColor=COLOR_TEXT
        ),
        "right_title": ParagraphStyle(
            "right_title", fontName=FONT_NAME, fontSize=10.5, leading=15,
            textColor=COLOR_TEXT
        ),
        "right_body": ParagraphStyle(
            "right_body", fontName=FONT_NAME, fontSize=9, leading=13,
            textColor=COLOR_TEXT
        ),
        "right_secondary": ParagraphStyle(
            "right_secondary", fontName=FONT_NAME, fontSize=8.5, leading=12,
            textColor=COLOR_TEXT_LIGHT
        ),
        "tag": ParagraphStyle(
            "tag", fontName=FONT_NAME, fontSize=8.5, leading=11,
            textColor=COLOR_MAIN, alignment=1
        ),
    }


# ===================== 页面绘制回调 =====================
def _draw_first_page(c, doc):
    """首页：画左右边框、左栏背景、头像（通过闭包读取 avatar_path）"""
    _, H = doc.pagesize
    c.setLineWidth(BORDER_WIDTH)
    c.setStrokeColor(COLOR_BORDER)
    # 左栏边框
    c.rect(MARGIN, MARGIN, LEFT_COL_WIDTH, H - 2 * MARGIN, stroke=1, fill=0)
    # 右栏边框
    c.rect(MARGIN + LEFT_COL_WIDTH + COL_SPACING, MARGIN, RIGHT_COL_WIDTH, H - 2 * MARGIN, stroke=1, fill=0)
    # 左栏顶部背景
    c.setFillColor(COLOR_LIGHT)
    c.rect(MARGIN, H - MARGIN - 45 * mm, LEFT_COL_WIDTH, 45 * mm, fill=1, stroke=0)
    c.setStrokeColor(COLOR_MAIN)
    c.rect(MARGIN, H - MARGIN - 45 * mm, LEFT_COL_WIDTH, 45 * mm, fill=0, stroke=1)
    # 中间分隔线
    c.setStrokeColor(COLOR_MAIN)
    c.setLineWidth(0.8)
    c.line(MARGIN + LEFT_COL_WIDTH, MARGIN, MARGIN + LEFT_COL_WIDTH, H - MARGIN)


def _draw_later_pages(c, doc):
    """第2/3…页：只画右边框"""
    _, H = doc.pagesize
    c.setLineWidth(BORDER_WIDTH)
    c.setStrokeColor(COLOR_BORDER)
    c.rect(MARGIN + LEFT_COL_WIDTH + COL_SPACING, MARGIN, RIGHT_COL_WIDTH, H - 2 * MARGIN, stroke=1, fill=0)


# ===================== 内容生成 =====================
def generate_left_col_content(fields: Dict, styles: Dict, avatar_path: str) -> List[Any]:
    """左栏：头像+姓名并排，基本信息，证书，技能，自我评价"""
    story = []

    # 头像 + 姓名/岗位 并排（Table布局）
    avatar_elem = [Spacer(1, AVATAR_SIZE)]
    name_elem = [Paragraph(fields["name"] or "求职候选人", styles["left_name"])]
    name_elem.append(Spacer(1, 2 * mm))
    simple_job = simplify_job_title(fields["job_intention"])
    if simple_job:
        name_elem.append(Paragraph(simple_job, styles["left_job"]))

    top_table = Table(
        [[avatar_elem, name_elem]],
        colWidths=[AVATAR_SIZE + 2 * mm, LEFT_COL_WIDTH - 2 * MODULE_PADDING - AVATAR_SIZE - 2 * mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (0, 0), "CENTER"),
            ("ALIGN", (1, 0), (1, 0), "LEFT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ])
    )
    story.append(top_table)
    story.append(Spacer(1, 6 * mm))

    # 基本信息
    story.append(Paragraph("基本信息", styles["left_title"]))
    story.append(Spacer(1, 3 * mm))
    base_info = [
        ("性别", fields["gender"]),
        ("政治面貌", fields["political_status"]),
        ("籍贯", fields["native_place"]),
        ("电话", fields["phone"]),
        ("邮箱", fields["email"]),
        ("微信", fields["wechat"]),
    ]
    for label, value in base_info:
        if value:
            story.append(Paragraph(f"{label}：{value}", styles["left_content"]))
            story.append(Spacer(1, 2 * mm))
    story.append(Spacer(1, 5 * mm))

    # 证书
    if fields["certificates"]:
        story.append(Paragraph("所获证书", styles["left_title"]))
        story.append(Spacer(1, 3 * mm))
        for cert in fields["certificates"]:
            story.append(Paragraph(safe_str(cert), styles["left_content"]))
            story.append(Spacer(1, 2 * mm))
        story.append(Spacer(1, 5 * mm))

    # 技能
    if fields["skills"]:
        story.append(Paragraph("专业技能", styles["left_title"]))
        story.append(Spacer(1, 3 * mm))
        skill_tags = [Paragraph(f" {safe_str(s)} ", styles["tag"]) for s in fields["skills"]]
        while len(skill_tags) % 2 != 0:
            skill_tags.append(Paragraph("", styles["tag"]))
        rows = [skill_tags[i:i + 2] for i in range(0, len(skill_tags), 2)]
        col_w = (LEFT_COL_WIDTH - 2 * MODULE_PADDING) / 2 - 2 * mm
        skill_table = Table(rows, colWidths=[col_w] * 2)
        skill_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), COLOR_GRAY_LIGHT),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(skill_table)
        story.append(Spacer(1, 5 * mm))

    # 自我评价（左栏底部）
    if fields["self_intro"]:
        story.append(Paragraph("自我评价", styles["left_title"]))
        story.append(Spacer(1, 3 * mm))
        intro = fields["self_intro"]
        if len(intro) > MAX_SELF_INTRO_LENGTH:
            intro = intro[:MAX_SELF_INTRO_LENGTH] + "..."
        story.append(Paragraph(intro, styles["left_content"]))

    return story


def generate_right_col_content(fields: Dict, styles: Dict) -> List[Any]:
    """右栏：教育、工作、校园、项目经历（支持跨页）"""
    story = []

    # 教育背景
    if fields["education"]:
        story.append(Paragraph("教育背景", styles["right_title"]))
        story.append(Spacer(1, 3 * mm))
        for edu in fields["education"]:
            school = safe_str(edu.get("school", ""))
            major = safe_str(edu.get("major", ""))
            degree = safe_str(edu.get("degree", ""))
            start = safe_str(edu.get("start", ""))
            end = safe_str(edu.get("end", ""))
            period = f"{start} - {end}" if (start or end) else ""
            header = " | ".join(filter(None, [school, degree, major]))
            story.append(Paragraph(f"<b>{header}</b>", styles["right_body"]))
            if period:
                story.append(Paragraph(period, styles["right_secondary"]))
            story.append(Spacer(1, 4 * mm))
        story.append(Spacer(1, 5 * mm))

    # 工作经历
    if fields["work_experience"]:
        story.append(Paragraph("工作经历", styles["right_title"]))
        story.append(Spacer(1, 3 * mm))
        for work in fields["work_experience"]:
            company = safe_str(work.get("company", ""))
            position = safe_str(work.get("position", ""))
            start = safe_str(work.get("start", ""))
            end = safe_str(work.get("end", ""))
            period = f"{start} - {end}" if (start or end) else ""
            description = safe_str(work.get("description", ""))
            story.append(Paragraph(f"<b>{company}</b> | {position}", styles["right_body"]))
            if period:
                story.append(Paragraph(period, styles["right_secondary"]))
            if description:
                for line in description.split("；"):
                    if line.strip():
                        story.append(Paragraph(f"• {line.strip()}", styles["right_body"]))
            story.append(Spacer(1, 4 * mm))
        story.append(Spacer(1, 5 * mm))

    # 校园经历
    if fields["campus_experience"]:
        story.append(Paragraph("校园经历", styles["right_title"]))
        story.append(Spacer(1, 3 * mm))
        for exp in fields["campus_experience"]:
            name = safe_str(exp.get("name", "") or exp.get("organization", ""))
            position = safe_str(exp.get("position", "") or exp.get("role", ""))
            start = safe_str(exp.get("start", ""))
            end = safe_str(exp.get("end", ""))
            period = f"{start} - {end}" if (start or end) else ""
            description = safe_str(exp.get("description", ""))
            header = f"<b>{name}</b>" + (f" | {position}" if position else "")
            story.append(Paragraph(header, styles["right_body"]))
            if period:
                story.append(Paragraph(period, styles["right_secondary"]))
            if description:
                for line in description.split("；"):
                    if line.strip():
                        story.append(Paragraph(f"• {line.strip()}", styles["right_body"]))
            story.append(Spacer(1, 4 * mm))
        story.append(Spacer(1, 5 * mm))

    # 项目经历
    if fields["project_experience"]:
        story.append(Paragraph("项目经历", styles["right_title"]))
        story.append(Spacer(1, 3 * mm))
        for proj in fields["project_experience"]:
            name = safe_str(proj.get("name", ""))
            start = safe_str(proj.get("start", ""))
            end = safe_str(proj.get("end", ""))
            period = f"{start} - {end}" if (start or end) else ""
            description = safe_str(proj.get("description", ""))
            duties = safe_str(proj.get("duties", ""))
            # 支持项目角色（负责人、开发成员等）
            role = safe_str(proj.get("role", ""))
            
            # 项目名称 + 角色（如果有）
            if role:
                project_title = f"<b>{name}</b> | {role}"
            else:
                project_title = f"<b>{name}</b>"
            story.append(Paragraph(project_title, styles["right_body"]))
            
            if period:
                story.append(Paragraph(period, styles["right_secondary"]))
            if description:
                story.append(Paragraph(f"项目描述：{description}", styles["right_body"]))
            if duties:
                for line in duties.split("；"):
                    if line.strip():
                        story.append(Paragraph(f"• {line.strip()}", styles["right_body"]))
            story.append(Spacer(1, 4 * mm))

    return story


# ===================== PDF 生成（核心） =====================
def generate_adaptive_resume(resume_data: Dict, output_path: Path) -> Path:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab 未安装，请运行: pip install reportlab")

    output_path = Path(str(output_path)).absolute()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    user_fields = get_all_user_fields(resume_data)
    avatar_path = user_fields["avatar"]
    styles = get_styles()

    left_content = generate_left_col_content(user_fields, styles, avatar_path)
    right_content = generate_right_col_content(user_fields, styles)

    # 定义 Frame
    left_frame = Frame(
        x1=MARGIN + MODULE_PADDING,
        y1=MARGIN + MODULE_PADDING,
        width=LEFT_COL_WIDTH - 2 * MODULE_PADDING,
        height=PAGE_H - 2 * MARGIN - 2 * MODULE_PADDING,
        id="left_frame",
        showBoundary=0,
    )
    right_frame_first = Frame(
        x1=MARGIN + LEFT_COL_WIDTH + COL_SPACING + MODULE_PADDING,
        y1=MARGIN + MODULE_PADDING,
        width=RIGHT_COL_WIDTH - 2 * MODULE_PADDING,
        height=PAGE_H - 2 * MARGIN - 2 * MODULE_PADDING,
        id="right_frame_first",
        showBoundary=0,
    )
    right_frame_only = Frame(
        x1=MARGIN + LEFT_COL_WIDTH + COL_SPACING + MODULE_PADDING,
        y1=MARGIN + MODULE_PADDING,
        width=RIGHT_COL_WIDTH - 2 * MODULE_PADDING,
        height=PAGE_H - 2 * MARGIN - 2 * MODULE_PADDING,
        id="right_frame_only",
        showBoundary=0,
    )

    # 第一页绘制（含头像）
    def _page1(c, doc):
        _draw_first_page(c, doc)
        if avatar_path and os.path.exists(avatar_path):
            try:
                _, H = doc.pagesize
                img_x = MARGIN + MODULE_PADDING
                img_y = H - MARGIN - MODULE_PADDING - AVATAR_SIZE
                c.drawImage(avatar_path, img_x, img_y,
                            width=AVATAR_SIZE, height=AVATAR_SIZE,
                            preserveAspectRatio=True)
            except Exception as e:
                logger.warning(f"头像绘制失败: {e}")

    doc = BaseDocTemplate(
        str(output_path), pagesize=PAGE_SIZE,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    doc.addPageTemplates([
        PageTemplate(id="page1", frames=[left_frame, right_frame_first], onPage=_page1),
        PageTemplate(id="page2", frames=[right_frame_only], onPage=_draw_later_pages),
    ])

    # 强制内容流：左栏 → 右栏（page1）→ 自动续页（page2+）
    story = []
    story.extend(left_content)
    story.append(FrameBreak())
    story.append(NextPageTemplate("page2"))
    story.extend(right_content)

    doc.build(story)
    logger.info(f"PDF生成: {output_path}")
    return output_path


# ===================== AI 优化函数 =====================
def optimize_resume_by_ai(
        resume_data: Dict, job_info: Dict, config: Config,
        options: Optional[Dict] = None,
) -> Dict:
    try:
        client = config.make_doubao_client()
        option_hints = ""
        if options:
            hints = []
            if options.get("add_missing_skills"):
                hints.append("在技能栏补充岗位要求但简历中未列出的技能")
            if options.get("add_metrics"):
                hints.append("为经历描述添加可量化的成果数据")
            if options.get("strengthen_summary"):
                hints.append("重写自我评价，突出与该岗位匹配的核心竞争力")
            if hints:
                option_hints = "\n额外优化要求：" + "；".join(hints)

        system_prompt = (
            "你是专业的简历优化师。根据用户的简历和目标岗位JD，输出针对该岗位优化后的简历JSON。\n\n"
            "【优化要求】\n"
            "1. 仔细分析岗位JD中的关键词、技能要求、职责描述\n"
            "2. 优化自我评价（self_intro）：根据岗位需求，重写自我评价，突出与岗位匹配的经验、技能和优势（200-300字）\n"
            "   - 即使原简历没有自我评价，也必须根据岗位JD和简历内容生成一个！\n"
            "3. 优化工作经历和项目经验的描述：使用与JD相关的关键词和行动动词，突出相关成果\n"
            "4. 优化技能列表：确保包含JD中要求的技能，删除与岗位无关的技能\n"
            "5. 保持简历的真实性，不虚构经历，但基于JD优化表述方式\n\n"
            "【输出格式】\n"
            "严格输出标准JSON，必须包含以下所有字段（如原简历没有该字段，则根据岗位JD生成一个或输出空列表/空字符串）：\n"
            "name、job_intention、age、gender、political_status、native_place、\n"
            "phone、email、wechat、\n"
            "certificates（列表）、\n"
            "education（列表，每项含school/degree/major/start/end）、\n"
            "work_experience（列表，每项含company/position/start/end/description）、\n"
            "campus_experience（列表，每项含name/position/start/end/description）、\n"
            "project_experience（列表，每项含name/start/end/description/duties）、\n"
            "skills（列表）、self_intro（字符串，200-300字，针对岗位优化后的自我评价，即使原简历没有也必须生成！）。\n\n"
            "【重要】只输出JSON，不要任何说明文字。保留简历中所有原有经历内容。"
            + option_hints
        )

        result = client.chat_json(
            messages=[{"role": "user", "content": json.dumps(
                {"resume": resume_data, "job": job_info}, ensure_ascii=False
            )}],
            system=system_prompt,
            temperature=0.1,
        )
        return result if isinstance(result, dict) and result else resume_data
    except Exception as e:
        logger.warning(f"AI调用降级：{str(e)}")
        return resume_data


# ===================== 主业务类 =====================
class ResumeTailor:
    def __init__(self, config: Config):
        self.config = config
        self.output_dir = Path(str(TAILORED_DIR)).absolute()
        os.makedirs(self.output_dir, exist_ok=True)

    def tailor(
            self, resume_data: Dict, job: Dict,
            output_dir: Optional[Path] = None,
            options: Optional[Dict] = None,
    ) -> Dict:
        try:
            optimized = optimize_resume_by_ai(resume_data, job, self.config, options=options)

            # AI 调用会丢失文件系统路径，从原始数据恢复头像
            # 尝试多种路径格式
            avatar = (
                safe_str(resume_data.get("avatar", ""))
                or safe_str(resume_data.get("photo_path", ""))
            )
            
            # 增强的头像路径检查
            avatar_path = None
            if avatar:
                logger.info(f"[头像] 原始头像路径: {avatar}")
                
                # 1. 原始路径（绝对路径）
                if os.path.exists(avatar):
                    avatar_path = avatar
                    logger.info(f"[头像] 原始路径存在: {avatar_path}")
                
                # 2. URL 格式：/uploads/filename -> backend/uploads/filename
                elif avatar.startswith('/uploads/') or avatar.startswith('\\uploads\\'):
                    filename = os.path.basename(avatar)
                    project_root = Path(__file__).parent.parent.parent
                    local_path = project_root / "backend" / "uploads" / filename
                    if local_path.exists():
                        avatar_path = str(local_path)
                        logger.info(f"[头像] 从URL转换找到: {avatar_path}")
                
                # 3. 其他相对路径尝试
                elif not avatar.startswith('http') and not avatar.startswith('file://'):
                    # 获取当前工作目录和项目根目录
                    cwd = Path.cwd()
                    project_root = Path(__file__).parent.parent.parent
                    
                    # 搜索路径列表
                    search_paths = [
                        cwd / avatar,
                        project_root / avatar,
                        project_root / "data" / avatar,
                        project_root / "data" / "photos" / avatar,
                        project_root / "backend" / avatar,
                        project_root / "backend" / "uploads" / avatar,
                        project_root / "photo" / avatar,
                        cwd / "data" / avatar,
                        cwd / "photo" / avatar,
                    ]
                    
                    for search_path in search_paths:
                        if search_path.exists():
                            avatar_path = str(search_path)
                            logger.info(f"[头像] 找到头像文件: {avatar_path}")
                            break
                    
                    # 如果只提供文件名，尝试在常见目录中搜索
                    if not avatar_path and '/' not in avatar and '\\' not in avatar:
                        for search_dir in [project_root / "photo", project_root / "data", cwd / "photo", cwd / "data"]:
                            if search_dir.exists():
                                for ext in ['', '.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                                    for found_file in search_dir.glob(f"*{avatar}{ext}"):
                                        if found_file.is_file():
                                            avatar_path = str(found_file)
                                            logger.info(f"[头像] 模糊匹配找到: {avatar_path}")
                                            break
                                    if avatar_path:
                                        break
                                if avatar_path:
                                    break
            
            if avatar_path:
                logger.info(f"[头像] 最终使用头像: {avatar_path}")
                optimized["avatar"] = avatar_path
            else:
                logger.warning(f"[头像] 未找到头像文件: {avatar}")

            user_fields = get_all_user_fields(optimized)
            name = safe_str(user_fields.get("name", "候选人"))
            # 优先使用实际匹配的岗位名称，确保文件名与岗位对应
            simple_job = simplify_job_title(
                job.get("title", "") or user_fields.get("job_intention", "")
            )
            contact = get_contact_info(user_fields)
            file_name = re.sub(r'[\\/*?:"<>|]', "", f"{name}_{simple_job}_{contact}.pdf")
            logger.info(f"[简历优化] 生成文件名: {file_name} (姓名={name}, 岗位={simple_job}, 联系方式={contact})")

            out_dir = Path(output_dir or self.output_dir).absolute()
            output_path = out_dir / file_name
            generate_adaptive_resume(optimized, output_path)

            return {
                "status": "success",
                "tailored_data": optimized,
                "pdf_path": str(output_path),
                "file_name": file_name,
                "changes": [],
            }
        except Exception as e:
            import traceback
            logger.error(f"简历生成失败：{str(e)}\n{traceback.format_exc()}")
            return {
                "status": "failed",
                "error": str(e),
                "pdf_path": "",
                "file_name": "生成失败_简历.pdf",
                "changes": [],
            }

    def generate_pdf_from_data(
            self, resume_data: Dict, output_path: Optional[Path] = None,
    ) -> Path:
        user_fields = get_all_user_fields(resume_data)
        if output_path is None:
            name = safe_str(user_fields.get("name", "候选人"))
            simple_job = simplify_job_title(user_fields.get("job_intention", ""))
            contact = get_contact_info(user_fields)
            file_name = re.sub(r'[\\/*?:"<>|]', "", f"{name}_{simple_job}_{contact}.pdf")
            logger.info(f"[简历优化] generate_pdf_from_data 生成文件名: {file_name}")
            output_path = self.output_dir / file_name
        return generate_adaptive_resume(resume_data, Path(output_path))
