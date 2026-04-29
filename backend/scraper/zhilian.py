"""智联招聘爬虫"""
import re
import sys
import hashlib
import random
import asyncio
import urllib.parse
import concurrent.futures
from typing import List

from backend.core.config import Config
from backend.utils.logger import logger
from backend.utils.date_utils import now_iso
from backend.scraper.base import BaseScraper
from backend.scraper.anti_detect.stealth import (
    check_playwright, create_browser_context, clean_text
)

BASE_URL = "https://www.zhaopin.com"
CITY_CODES = {
    "全国": "530", "北京": "530", "上海": "538", "广州": "763", "深圳": "765",
    "杭州": "653", "成都": "801", "南京": "635", "武汉": "736", "西安": "854",
    "重庆": "551", "苏州": "636", "天津": "531", "青岛": "532", "长沙": "740",
}
JD_SELECTORS = [
    ".describtion", ".job-item-text", "[class*='describtion']",
    "[class*='job-item-text']", ".job-desc", ".description", "article"
]


def _parse_salary(sal: str):
    if not sal:
        return None, None
    m = re.search(r"(\d+)[Kk]-(\d+)[Kk]", sal)
    if m:
        return int(m.group(1)) * 1000, int(m.group(2)) * 1000
    m = re.search(r"(\d+)[^0-9]+(\d+)\s*元", sal)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)[^0-9]+(\d+)", sal)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    return None, None


class ZhilianScraper(BaseScraper):
    platform = "zhilian"

    def __init__(self, config: Config):
        super().__init__(config)

    def scrape(self, keyword: str, city: str = "全国", max_pages: int = 5) -> List[dict]:
        check_playwright()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._run_in_thread, keyword, city, max_pages)
            return future.result()

    def _run_in_thread(self, keyword, city, max_pages):
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._async_scrape(keyword, city, max_pages))
        finally:
            loop.close()

    async def _async_scrape(self, keyword, city, max_pages) -> List[dict]:
        from playwright.async_api import async_playwright, TimeoutError as PwTimeout
        logger.info(f"[zhilian] 开始: keyword={keyword}, city={city}")
        all_jobs = []
        city_code = CITY_CODES.get(city, "530")
        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()
            try:
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(random.uniform(3.0, 5.0))
            except Exception:
                pass

            for page_num in range(1, max_pages + 1):
                kw_enc = urllib.parse.quote(keyword)
                url = f"{BASE_URL}/jobs?keywords={kw_enc}&cityId={city_code}&workExperience=116&page={page_num}"
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if resp and resp.status not in (200, 304):
                        break
                except PwTimeout:
                    break
                await asyncio.sleep(random.uniform(3.0, 5.0))
                try:
                    await page.wait_for_selector(".job-list-item", timeout=8000)
                except Exception:
                    pass
                jobs = await self._extract_listing(page, city)
                if not jobs:
                    break
                for job in jobs:
                    if job.get("url"):
                        desc, email = await self._fetch_jd(page, job["url"])
                        if desc:
                            job["description"] = desc
                        if email:
                            job["contact_email"] = email
                        await asyncio.sleep(random.uniform(2.0, 4.0))
                all_jobs.extend(jobs)
                await asyncio.sleep(random.uniform(2.0, 4.0))
            await browser.close()
        logger.info(f"[zhilian] 共获取 {len(all_jobs)} 条")
        return all_jobs

    async def _fetch_jd(self, page, url: str) -> tuple:
        """获取职位详情描述和联系方式邮箱
        
        Returns:
            tuple: (description, contact_email)
        """
        description = ""
        contact_email = ""
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(random.uniform(2.0, 3.0))
            
            # 获取页面文本用于提取邮箱
            page_text = await page.evaluate(
                "() => { const clone = document.body.cloneNode(true); "
                "['script','style','nav','header','footer','aside'].forEach(t => "
                "clone.querySelectorAll(t).forEach(e => e.remove())); return clone.innerText; }"
            )
            
            # 提取邮箱
            contact_email = self._extract_email_from_text(page_text)
            
            # 获取职位描述
            for sel in JD_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        text = clean_text(await el.inner_text())
                        if len(text) >= 30:
                            description = text[:5000]
                            break
                except Exception:
                    continue
                    
            if not description and page_text:
                if '联系方式' in page_text:
                    page_text = page_text.split('联系方式')[0]
                description = page_text[:5000]
            
            if contact_email:
                logger.info(f"[zhilian] 找到邮箱: {contact_email}")
                
        except Exception as e:
            logger.debug(f"[zhilian] 获取详情失败: {e}")
            
        return description, contact_email

    async def _extract_listing(self, page, city: str) -> List[dict]:
        jobs = []
        items = await page.query_selector_all(".job-list-item")
        if not items:
            items = await page.query_selector_all("[class*='job-list-item']")
        for el in items:
            try:
                title_el = await el.query_selector(".job-name")
                title = clean_text(await title_el.inner_text()) if title_el else ""
                if not title:
                    continue
                company_el = await el.query_selector(".company-name")
                company = clean_text(await company_el.inner_text()) if company_el else ""
                sal_el = await el.query_selector(".job-salary")
                salary_text = clean_text(await sal_el.inner_text()) if sal_el else ""
                href = ""
                a_el = await el.query_selector("a[href]")
                if a_el:
                    href = await a_el.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href
                job_id = hashlib.md5((href or title + company).encode()).hexdigest()
                sal_min, sal_max = _parse_salary(salary_text)
                jobs.append(self._normalize_job({
                    "platform": self.platform, "job_id": job_id, "title": title,
                    "company": company, "city": city, "salary_min": sal_min,
                    "salary_max": sal_max, "skills": [], "description": "", "url": href,
                    "scraped_at": now_iso(),
                }, self.platform))
            except Exception as e:
                logger.debug(f"[zhilian] 解析异常: {e}")
        return jobs
