"""爬虫基类"""
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from backend.core.config import Config
from backend.utils.logger import logger


class BaseScraper(ABC):
    platform = "base"

    def __init__(self, config: Config):
        self.config = config

    @abstractmethod
    def scrape(self, keyword: str, city: str = "全国", max_pages: int = 5) -> List[dict]:
        pass

    @staticmethod
    def _extract_email_from_text(text: str) -> Optional[str]:
        """从文本中提取邮箱地址
        
        常见模式：
        - hr@company.com
        - hr@xxx.edu.cn
        - 邮箱：xxx@xxx.com
        - 投递邮箱：xxx@xxx.com
        - 联系邮箱：xxx@xxx.com
        - recruitment@company.com
        - zhaopin@company.com
        """
        if not text:
            return None
            
        # 邮箱正则表达式
        email_pattern = r'[\w\.-]+@[\w\.-]+\.\w{2,}'
        
        # 常见邮箱关键词上下文（提高准确性）
        email_keywords = [
            '邮箱', 'Email', 'E-mail', '联系邮箱', '投递邮箱', 
            '简历投递', '招聘邮箱', 'HR邮箱', '联系邮箱', '面试邮箱'
        ]
        
        # 在关键词附近查找邮箱
        for keyword in email_keywords:
            # 匹配 "关键词: xxx@xxx.com" 或 "关键词 xxx@xxx.com"
            pattern = rf'{keyword}[：:]\s*({email_pattern})'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        # 查找所有邮箱，选择最可能是HR/招聘邮箱的那个
        all_emails = re.findall(email_pattern, text, re.IGNORECASE)
        
        if not all_emails:
            return None
            
        # 优先选择包含 hr, recruitment, zhaopin, hire, career, job 等关键词的邮箱
        priority_keywords = ['hr', 'recruit', 'zhaopin', 'hire', 'career', 'job', 'apply', '投递', '招聘']
        for email in all_emails:
            email_lower = email.lower()
            if any(kw in email_lower for kw in priority_keywords):
                return email
        
        # 如果没有优先邮箱，返回第一个（通常是联系邮箱）
        return all_emails[0]

    def _normalize_job(self, job: dict, platform: str) -> dict:
        return {
            "platform": platform,
            "job_id": job.get("job_id", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "city": job.get("city", ""),
            "district": job.get("district", ""),
            "salary_min": job.get("salary_min"),
            "salary_max": job.get("salary_max"),
            "education": job.get("education", "不限"),
            "experience": job.get("experience", ""),
            "industry": job.get("industry", ""),
            "skills": job.get("skills", []),
            "description": job.get("description", ""),
            "url": job.get("url", ""),
            "contact_email": job.get("contact_email", ""),
            "company_size": job.get("company_size", ""),
            "posted_date": job.get("posted_date", ""),
            "scraped_at": job.get("scraped_at", ""),
        }
