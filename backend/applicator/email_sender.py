"""邮件自动投递"""
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.header import Header  # RFC2047 中文编码支持
from email.utils import formataddr
from pathlib import Path
from typing import Optional
import json

from backend.core.config import Config
from backend.utils.logger import logger

_COVER_LETTER_TEMPLATE = """\
您好！

我叫{name}，在贵公司招聘平台看到了「{title}」实习岗位，非常感兴趣，特此投递简历。

{custom_intro}

我的技能方向涵盖：{skills}。希望能有机会加入贵团队，为{company}的发展贡献自己的力量。

随邮附上个人简历，期待您的回复！

此致
{name}""".strip()


def build_cover_letter(name: str, title: str, company: str, skills: list, custom_intro: str = "") -> str:
    skills_str = "、".join(skills[:6]) if skills else "相关技术"
    default_intro = f"我目前正在积极寻找实习机会，「{title}」岗位与我的学习方向高度匹配。"
    return _COVER_LETTER_TEMPLATE.format(
        name=name, title=title, company=company,
        skills=skills_str, custom_intro=custom_intro or default_intro,
    )


class EmailApplicator:
    def __init__(self, config: Config):
        self.config = config
        if not config.smtp_email:
            raise ValueError("未配置发件邮箱（SMTP_EMAIL）")
        if not config.smtp_password:
            raise ValueError("未配置邮箱授权码（SMTP_PASSWORD）")

    def apply(self, job: dict, resume_path: Path, applicant_name: str = "",
              custom_intro: str = "", to_email: Optional[str] = None) -> dict:
        recipient = to_email or job.get("contact_email", "")
        if not recipient:
            return {"success": False, "error": "岗位无联系邮箱"}

        title = job.get("title", "实习生")
        company = job.get("company", "贵公司")
        skills = job.get("skills") or []
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except Exception:
                skills = [skills]

        resume_path = Path(resume_path)
        if not resume_path.exists():
            return {"success": False, "error": f"简历文件不存在: {resume_path}"}

        name = applicant_name or self.config.smtp_email.split("@")[0]
        subject = f"[实习申请] {title} - {name}"
        body = build_cover_letter(name, title, company, skills, custom_intro)

        try:
            msg = self._build_message(subject, body, recipient, resume_path, name)
            self._send(msg, recipient)
            logger.info(f"[email] 投递成功: {title} @ {company} → {recipient}")
            return {"success": True, "message": f"已发送至 {recipient}"}
        except smtplib.SMTPException as e:
            return {"success": False, "error": f"SMTP 发送失败: {e}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _build_message(self, subject, body, recipient, resume_path, sender_name):
        """构建邮件，From头部严格遵循RFC5322/RFC2047以通过QQ邮箱SMTP校验"""
        msg = MIMEMultipart()

        # 方案: 手动构造 RFC2047 编码的 From 头部
        # 格式: =?charset?encoding?encoded_text?=
        # 例: From: =?utf-8?b?5a6L55S15p2l?= <2664453066@qq.com>
        encoded_name = Header(sender_name, 'utf-8').encode()
        msg['From'] = f"{encoded_name} <{self.config.smtp_email}>"
        msg['To'] = recipient
        msg['Subject'] = Header(subject, 'utf-8')

        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        with open(resume_path, 'rb') as f:
            part = MIMEApplication(f.read(), _subtype='pdf')
            part.add_header('Content-Disposition', 'attachment', filename=resume_path.name)
            msg.attach(part)
        return msg

    def _send(self, msg, recipient):
        host = self.config.smtp_host
        port = self.config.smtp_port
        user = self.config.smtp_email
        password = self.config.smtp_password
        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=ctx) as server:
                server.login(user, password)
                server.sendmail(user, recipient, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(user, recipient, msg.as_string())
