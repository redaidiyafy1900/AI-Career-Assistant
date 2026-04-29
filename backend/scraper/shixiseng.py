"""实习僧爬虫"""
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
    check_playwright, create_browser_context, clean_text, parse_salary
)

BASE_URL = "https://www.shixiseng.com"
CITY_MAP = {
    "全国": "", "北京": "beijing", "上海": "shanghai", "广州": "guangzhou",
    "深圳": "shenzhen", "杭州": "hangzhou", "成都": "chengdu", "南京": "nanjing",
    "武汉": "wuhan", "西安": "xian", "重庆": "chongqing", "苏州": "suzhou",
    "天津": "tianjin", "青岛": "qingdao", "长沙": "changsha",
}
JD_SELECTORS = [
    ".jd-content", ".intern-detail .content", ".intern-detail__desc",
    "[class*='jd-content']", "[class*='job-desc']", ".description", "article"
]


class ShixisengScraper(BaseScraper):
    platform = "shixiseng"

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
        logger.info(f"[shixiseng] 开始: keyword={keyword}, city={city}")
        all_jobs = []
        city_en = CITY_MAP.get(city, "")
        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()
            try:
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(random.uniform(1.5, 3.0))
            except Exception:
                pass

            for page_num in range(1, max_pages + 1):
                kw_enc = urllib.parse.quote(keyword)
                url = (f"{BASE_URL}/interns?keyword={kw_enc}&city={city_en}&page={page_num}"
                       if city_en else f"{BASE_URL}/interns?keyword={kw_enc}&page={page_num}")
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if resp and resp.status not in (200, 304):
                        break
                except PwTimeout:
                    break
                await asyncio.sleep(random.uniform(2.0, 3.5))
                try:
                    await page.wait_for_selector(".intern-item", timeout=8000)
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
                await asyncio.sleep(random.uniform(1.5, 3.0))
            await browser.close()
        logger.info(f"[shixiseng] 共获取 {len(all_jobs)} 条")
        return all_jobs

    async def _fetch_jd(self, page, url: str) -> tuple:
        """获取职位详情描述和联系方式邮箱
        
        Returns:
            tuple: (description, contact_email)
        """
        description = ""
        contact_email = ""
        
        from playwright.async_api import TimeoutError as PwTimeout
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
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
                    
            # 如果没有找到指定选择器
            if not description and page_text:
                # 去掉联系方式部分
                if '联系方式' in page_text:
                    page_text = page_text.split('联系方式')[0]
                if 'HR' in page_text:
                    page_text = page_text.split('HR')[0]
                description = page_text[:5000]
            
            if contact_email:
                logger.info(f"[shixiseng] 找到邮箱: {contact_email}")
            
        except Exception as e:
            logger.debug(f"[shixiseng] 获取详情失败: {e}")
            
        return description, contact_email

    async def _extract_listing(self, page, city: str) -> List[dict]:
        jobs = []
        items = []
        for sel in [".intern-item", "[class*='intern-item']", ".job-item"]:
            items = await page.query_selector_all(sel)
            if items:
                break
        for el in items:
            try:
                title = ""
                for t_sel in [".title", ".job-name", "h3", "h4", "[class*='title']", "a"]:
                    t_el = await el.query_selector(t_sel)
                    if t_el:
                        title = clean_text(await t_el.inner_text())
                        if title and len(title) > 1:
                            break
                if not title:
                    continue
                company = ""
                for c_sel in [".company", ".firm", "[class*='company']"]:
                    c_el = await el.query_selector(c_sel)
                    if c_el:
                        company = clean_text(await c_el.inner_text())
                        if company:
                            break
                salary_text = ""
                for s_sel in [".pay-box", ".salary", "[class*='salary']", "[class*='pay']"]:
                    s_el = await el.query_selector(s_sel)
                    if s_el:
                        salary_text = clean_text(await s_el.inner_text())
                        if salary_text:
                            break
                href = ""
                a_el = await el.query_selector("a[href]")
                if a_el:
                    href = await a_el.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href
                m = re.search(r"/intern/([^/?#]+)", href)
                job_id = m.group(1) if m else hashlib.md5(
                    (href or title + company).encode()).hexdigest()
                sal_min, sal_max = parse_salary(salary_text)
                jobs.append(self._normalize_job({
                    "platform": self.platform, "job_id": job_id, "title": title,
                    "company": company, "city": city, "salary_min": sal_min,
                    "salary_max": sal_max, "skills": [], "description": "", "url": href,
                    "scraped_at": now_iso(),
                }, self.platform))
            except Exception as e:
                logger.debug(f"[shixiseng] 解析异常: {e}")
        return jobs
