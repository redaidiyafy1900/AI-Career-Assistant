"""全局配置管理 — 适配 D:\AI 项目"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

# 项目根目录（D:\AI）
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RESUMES_DIR = DATA_DIR / "resumes"
TAILORED_DIR = DATA_DIR / "tailored"
EXPORTS_DIR = DATA_DIR / "exports"
DB_PATH = DATA_DIR / "career.db"


def _ensure_dirs():
    for d in [RESUMES_DIR, TAILORED_DIR, EXPORTS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _clean(val: str) -> str:
    return val.strip().strip('"').strip("'").strip()


@dataclass
class Config:
    """应用配置"""
    doubao_api_key: str = "af6ff3bf-f66a-4652-8043-0cc1142abdd4"
    doubao_model: str = "ep-20260329183523-7ns5h"

    # FastGPT（面试功能）
    fastgpt_base_url: str = ""
    interview_fastgpt_api_key: str = ""
    interview_fastgpt_app_id: str = ""

    # SMTP
    smtp_host: str = "smtp.qq.com"
    smtp_port: int = 465
    smtp_email: str = ""
    smtp_password: str = ""

    # 平台账号（仅投递时需要）
    boss_username: str = ""
    boss_password: str = ""

    # 采集参数
    scrape_delay_min: float = 1.5
    scrape_delay_max: float = 4.0
    max_pages_per_search: int = 5

    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)
    db_path: Path = field(default_factory=lambda: DB_PATH)

    @classmethod
    def load(cls) -> "Config":
        env_path = PROJECT_ROOT / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
        else:
            load_dotenv(override=True)
        _ensure_dirs()

        return cls(
            doubao_api_key=_clean(os.getenv("DOUBAO_API_KEY", "af6ff3bf-f66a-4652-8043-0cc1142abdd4")),
            doubao_model=_clean(os.getenv("DOUBAO_MODEL", "ep-20260329183523-7ns5h")),
            fastgpt_base_url=_clean(os.getenv("FASTGPT_BASE_URL", "")),
            interview_fastgpt_api_key=_clean(os.getenv("INTERVIEW_FASTGPT_API_KEY", "")),
            interview_fastgpt_app_id=_clean(os.getenv("INTERVIEW_FASTGPT_APP_ID", "")),
            smtp_host=_clean(os.getenv("SMTP_HOST", "smtp.qq.com")),
            smtp_port=int(_clean(os.getenv("SMTP_PORT", "465")) or "465"),
            smtp_email=_clean(os.getenv("SMTP_EMAIL", "")),
            smtp_password=_clean(os.getenv("SMTP_PASSWORD", "")),
            boss_username=_clean(os.getenv("BOSS_USERNAME", "")),
            boss_password=_clean(os.getenv("BOSS_PASSWORD", "")),
        )

    def make_doubao_client(self):
        from backend.utils.doubao_client import DoubaoClient
        return DoubaoClient(api_key=self.doubao_api_key, model=self.doubao_model)
