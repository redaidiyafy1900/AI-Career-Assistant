"""BOSS直聘爬虫"""
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

BASE_URL = "https://www.zhipin.com"
CITY_CODES = {
    "全国": "100010000", "北京": "101010100", "上海": "101020100", "广州": "101280100",
    "深圳": "101280600", "杭州": "101210100", "成都": "101270100", "南京": "101190100",
    "武汉": "101200100", "西安": "101110100", "重庆": "101040100", "苏州": "101190400",
    "天津": "101030100", "青岛": "101120200", "长沙": "101250100",
}
JD_SELECTORS = [
    ".job-sec-text", ".job-detail__main", ".job-detail",
    "[class*='job-sec-text']", "[class*='job-detail']", ".desc", "article"
]


def _parse_salary(sal: str):
    m = re.search(r"(\d+)-(\d+)[Kk]", sal or "", re.I)
    if m:
        return int(m.group(1)) * 1000, int(m.group(2)) * 1000
    m = re.search(r"(\d+)[Kk]以上", sal or "", re.I)
    if m:
        return int(m.group(1)) * 1000, None
    m = re.search(r"(\d+)-(\d+)\s*元", sal or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


class BossScraper(BaseScraper):
    platform = "boss"

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
        logger.info(f"[boss] 开始: keyword={keyword}, city={city}")
        all_jobs = []
        city_code = CITY_CODES.get(city, "100010000")
        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()
            try:
                await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(random.uniform(2.0, 4.0))
            except Exception:
                pass

            for page_num in range(1, max_pages + 1):
                kw_enc = urllib.parse.quote(keyword)
                url = f"{BASE_URL}/web/geek/job?query={kw_enc}&city={city_code}&internship=1&page={page_num}"
                try:
                    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    if resp and resp.status not in (200, 304):
                        break
                except PwTimeout:
                    break
                await asyncio.sleep(random.uniform(2.0, 4.0))
                try:
                    await page.wait_for_selector(".job-card-wrapper", timeout=8000)
                except Exception:
                    pass
                jobs = await self._extract_listing(page, city)
                if not jobs:
                    break
                for job in jobs:
                    if job.get("url"):
                        jd = await self._fetch_jd(page, job["url"])
                        if jd:
                            job["description"] = jd
                        await asyncio.sleep(random.uniform(2.0, 5.0))
                all_jobs.extend(jobs)
                await asyncio.sleep(random.uniform(1.5, 3.0))
            await browser.close()
        logger.info(f"[boss] 共获取 {len(all_jobs)} 条")
        return all_jobs

    async def _fetch_jd(self, page, url: str) -> str:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await asyncio.sleep(random.uniform(2.0, 3.0))
            for sel in JD_SELECTORS:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        text = clean_text(await el.inner_text())
                        if len(text) >= 30:
                            return text[:5000]
                except Exception:
                    continue
            return ""
        except Exception:
            return ""

    async def _extract_listing(self, page, city: str) -> List[dict]:
        jobs = []
        items = await page.query_selector_all(".job-card-wrapper")
        if not items:
            items = await page.query_selector_all("[class*='job-card']")
        for el in items:
            try:
                title_el = await el.query_selector(".job-name")
                if not title_el:
                    title_el = await el.query_selector("a[class*='job']")
                title = clean_text(await title_el.inner_text()) if title_el else ""
                if not title:
                    continue
                company_el = await el.query_selector(".company-name")
                company = clean_text(await company_el.inner_text()) if company_el else ""
                sal_el = await el.query_selector(".salary")
                salary_text = clean_text(await sal_el.inner_text()) if sal_el else ""
                href = ""
                a_el = await el.query_selector("a[href*='/job_detail/']")
                if a_el:
                    href = await a_el.get_attribute("href") or ""
                    if href and not href.startswith("http"):
                        href = BASE_URL + href
                m = re.search(r"/job_detail/([^/?#.]+)", href)
                job_id = m.group(1) if m else hashlib.md5((href or title + company).encode()).hexdigest()
                sal_min, sal_max = _parse_salary(salary_text)
                jobs.append(self._normalize_job({
                    "platform": self.platform, "job_id": job_id, "title": title,
                    "company": company, "city": city, "salary_min": sal_min,
                    "salary_max": sal_max, "skills": [], "description": "", "url": href,
                    "scraped_at": now_iso(),
                }, self.platform))
            except Exception as e:
                logger.debug(f"[boss] 解析异常: {e}")
        return jobs
