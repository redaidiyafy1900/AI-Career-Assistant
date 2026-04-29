"""前程无忧爬虫 - 改进版"""
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

SEARCH_URL = "https://we.51job.com/pc/search"
CITY_CODES = {
    "全国": "000000", "北京": "010000", "上海": "020000", "广州": "030200",
    "深圳": "040000", "杭州": "080200", "成都": "090200", "南京": "070200",
    "武汉": "180200", "西安": "200200", "重庆": "060000", "苏州": "070300",
    "天津": "050000", "青岛": "150600", "长沙": "170200",
}
JD_SELECTORS = [
    ".job_msg", ".ql-editor", "#description", ".jobdesc",
    ".job-detail__desc", "[class*='job_msg']", "[class*='jobdesc']", "article"
]


def _parse_salary(sal: str):
    if not sal or sal in ("面议", "薪资面议", "-"):
        return None, None
    m = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*万/月", sal)
    if m:
        return int(float(m.group(1)) * 10000), int(float(m.group(2)) * 10000)
    m = re.search(r"(\d+)-(\d+)\s*元/月", sal)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)-(\d+)\s*元/天", sal)
    if m:
        return int(m.group(1)) * 22, int(m.group(2)) * 22
    m = re.search(r"(\d+)[^0-9]+(\d+)", sal)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    return None, None


class WuyouScraper(BaseScraper):
    platform = "wuyou"
    
    # 备用搜索URL
    BACKUP_SEARCH_URL = "https://search.51job.com"

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
        logger.info(f"[前程无忧] Starting: keyword={keyword}, city={city}")
        
        all_jobs = []
        city_code = CITY_CODES.get(city, "000000")
        
        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()
            
            # 设置额外的请求头
            await page.set_extra_http_headers({
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            })

            for page_num in range(1, max_pages + 1):
                # 构建URL
                params = {
                    "keyword": keyword, 
                    "searchType": "2", 
                    "pageNum": str(page_num),
                    "pageSize": "20", 
                    "city": city_code, 
                    "degree": "",
                    "isInternship": "1",
                }
                url = SEARCH_URL + "?" + urllib.parse.urlencode(params)
                
                try:
                    logger.info(f"[前程无忧] Page {page_num}: {url[:80]}...")
                    resp = await page.goto(url, wait_until="networkidle", timeout=45000)
                    
                    if resp and resp.status not in (200, 304):
                        logger.warning(f"[前程无忧] Page {page_num}: HTTP {resp.status}")
                        continue
                        
                except PwTimeout:
                    logger.warning(f"[前程无忧] Page {page_num}: Timeout")
                    continue
                except Exception as e:
                    logger.warning(f"[前程无忧] Page {page_num}: {e}")
                    continue
                    
                await asyncio.sleep(random.uniform(2.0, 4.0))
                
                # 提取数据
                jobs = await self._extract_listing(page, city)
                
                if not jobs:
                    logger.info(f"[前程无忧] Page {page_num}: No jobs found, trying backup selectors...")
                    jobs = await self._extract_listing_backup(page, city)
                    
                if not jobs:
                    logger.info(f"[前程无忧] Page {page_num}: Still no jobs, stopping")
                    break
                    
                logger.info(f"[前程无忧] Page {page_num}: Got {len(jobs)} jobs")
                
                for job in jobs:
                    if job.get("url"):
                        desc, email = await self._fetch_jd(page, job["url"])
                        if desc:
                            job["description"] = desc
                        if email:
                            job["contact_email"] = email
                        await asyncio.sleep(random.uniform(1.5, 3.0))
                        
                all_jobs.extend(jobs)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                
            await browser.close()
            
        logger.info(f"[前程无忧] Total: {len(all_jobs)} jobs")
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
                    
            # 如果没有找到指定选择器，尝试从页面文本中提取职位描述部分
            if not description and page_text:
                # 去掉联系方式部分
                if '联系方式' in page_text:
                    page_text = page_text.split('联系方式')[0]
                if '联系邮箱' in page_text:
                    page_text = page_text.split('联系邮箱')[0]
                description = page_text[:5000]
            
            if contact_email:
                logger.info(f"[前程无忧] 找到邮箱: {contact_email}")
                
        except Exception as e:
            logger.debug(f"[前程无忧] 获取详情失败: {e}")
            
        return description, contact_email

    async def _extract_listing(self, page, city: str) -> List[dict]:
        """主提取方法"""
        jobs = []
        
        # 尝试多种选择器
        selectors = [
            ".joblist-box__item",
            ".e-list-item",
            ".job_item",
            "[class*='joblist-box']",
            "[class*='job-item']",
            ".joblist .job",
        ]
        
        for sel in selectors:
            items = await page.query_selector_all(sel)
            if items:
                logger.info(f"[前程无忧] Selector '{sel}' found {len(items)} items")
                for el in items:
                    job = await self._extract_single_job(el, city)
                    if job:
                        jobs.append(job)
                if jobs:
                    break
                    
        return jobs

    async def _extract_listing_backup(self, page, city: str) -> List[dict]:
        """备用提取方法 - 使用更宽泛的选择器"""
        jobs = []
        
        # 获取页面HTML来分析结构
        try:
            html = await page.content()
            
            # 尝试从script标签中提取JSON数据
            scripts = await page.query_selector_all("script")
            for script in scripts:
                try:
                    text = await script.inner_text()
                    if 'jobList' in text or 'job_list' in text or 'positionList' in text:
                        logger.info("[前程无忧] Found job data in script tag")
                        break
                except:
                    continue
                    
            # 尝试从所有链接中提取
            links = await page.query_selector_all("a[href*='51job.com']")
            for link in links[:30]:
                try:
                    href = await link.get_attribute("href") or ""
                    title_el = await link.query_selector("span") or link
                    title = clean_text(await title_el.inner_text())
                    
                    if title and len(title) > 3 and '51job' in href:
                        job_id = hashlib.md5((href + title).encode()).hexdigest()
                        jobs.append(self._normalize_job({
                            "platform": self.platform, "job_id": job_id, "title": title,
                            "company": "", "city": city, "salary_min": None,
                            "salary_max": None, "skills": [], "description": "", "url": href,
                            "scraped_at": now_iso(),
                        }, self.platform))
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"[前程无忧] Backup extraction failed: {e}")
            
        return jobs

    async def _extract_single_job(self, el, city: str) -> dict:
        """从元素中提取单个职位"""
        try:
            # 获取标题
            title = ""
            title_el = await el.query_selector(".jname")
            if not title_el:
                title_el = await el.query_selector("a.title")
            if not title_el:
                title_el = await el.query_selector("a")
            if title_el:
                title = clean_text(await title_el.inner_text())
                
            if not title or len(title) < 3:
                return None
                
            # 获取公司
            company = ""
            company_el = await el.query_selector(".cname")
            if not company_el:
                company_el = await el.query_selector(".company-name")
            if company_el:
                company = clean_text(await company_el.inner_text())
                
            # 获取薪资
            salary_text = ""
            sal_el = await el.query_selector(".sal")
            if not sal_el:
                sal_el = await el.query_selector(".salary")
            if sal_el:
                salary_text = clean_text(await sal_el.inner_text())
                
            # 获取链接
            href = ""
            a_el = await el.query_selector("a[href*='51job.com']")
            if not a_el:
                a_el = await el.query_selector("a")
            if a_el:
                href = await a_el.get_attribute("href") or ""
                
            job_id = hashlib.md5((href or title + company).encode()).hexdigest()
            sal_min, sal_max = _parse_salary(salary_text)
            
            return self._normalize_job({
                "platform": self.platform, "job_id": job_id, "title": title,
                "company": company, "city": city, "salary_min": sal_min,
                "salary_max": sal_max, "skills": [], "description": "", "url": href,
                "scraped_at": now_iso(),
            }, self.platform)
            
        except Exception as e:
            logger.debug(f"[前程无忧] Extract job failed: {e}")
            return None
