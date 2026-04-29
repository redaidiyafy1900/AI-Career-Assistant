"""大厂官网 + 其他企业官网爬虫（通用模式）"""
import re
import sys
import hashlib
import random
import asyncio
import concurrent.futures
from typing import List

from backend.core.config import Config
from backend.utils.logger import logger
from backend.utils.date_utils import now_iso
from backend.scraper.base import BaseScraper
from backend.scraper.anti_detect.stealth import (
    check_playwright, create_browser_context, clean_text
)

# 大厂招聘官网配置
ENTERPRISE_SITES = {
    "字节跳动": {
        "search_url": "https://jobs.bytedance.com/campus/position?category=6704215862393532681&location=CT_156&project=&type=3&keyword={keyword}",
        "item_sel": ".position-item",
        "title_sel": ".position-name",
        "company": "字节跳动",
        "jd_sels": [".position-info", ".job-detail", ".description", "article"],
    },
    "腾讯": {
        "search_url": "https://careers.tencent.com/campusrecruit.html?keyword={keyword}",
        "item_sel": ".campus-job-item",
        "title_sel": ".pc-tl",
        "company": "腾讯",
        "jd_sels": [".recruit-detail", ".job-description", "article"],
    },
    "阿里巴巴": {
        "search_url": "https://talent.alibaba.com/campus/position-list?positionName={keyword}",
        "item_sel": ".position-item",
        "title_sel": ".position-name",
        "company": "阿里巴巴",
        "jd_sels": [".position-desc", ".job-info", "article"],
    },
}


class EnterpriseScraper(BaseScraper):
    platform = "enterprise"

    def __init__(self, config: Config):
        super().__init__(config)

    def scrape(self, keyword: str, city: str = "全国", max_pages: int = 3) -> List[dict]:
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
        from playwright.async_api import async_playwright
        logger.info(f"[enterprise] 开始: keyword={keyword}")
        all_jobs = []
        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()

            for company_name, site_cfg in ENTERPRISE_SITES.items():
                url = site_cfg["search_url"].format(keyword=keyword)
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.uniform(3.0, 5.0))
                    items = await page.query_selector_all(site_cfg["item_sel"])
                    for el in items[:20]:
                        try:
                            title_el = await el.query_selector(site_cfg["title_sel"])
                            title = clean_text(await title_el.inner_text()) if title_el else ""
                            if not title:
                                continue
                            href = ""
                            a_el = await el.query_selector("a[href]")
                            if a_el:
                                href = await a_el.get_attribute("href") or ""
                            job_id = hashlib.md5((company_name + title).encode()).hexdigest()
                            description = ""
                            if href:
                                try:
                                    await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                                    await asyncio.sleep(random.uniform(1.5, 3.0))
                                    for jd_sel in site_cfg["jd_sels"]:
                                        jd_el = await page.query_selector(jd_sel)
                                        if jd_el:
                                            text = clean_text(await jd_el.inner_text())
                                            if len(text) >= 30:
                                                description = text[:5000]
                                                break
                                    await page.go_back()
                                    await asyncio.sleep(random.uniform(1.0, 2.0))
                                except Exception:
                                    pass
                            all_jobs.append(self._normalize_job({
                                "platform": self.platform,
                                "job_id": job_id,
                                "title": title,
                                "company": company_name,
                                "city": city,
                                "description": description,
                                "url": href,
                                "scraped_at": now_iso(),
                            }, self.platform))
                        except Exception as e:
                            logger.debug(f"[enterprise] {company_name} 解析异常: {e}")
                except Exception as e:
                    logger.warning(f"[enterprise] {company_name} 访问失败: {e}")
                await asyncio.sleep(random.uniform(2.0, 4.0))
            await browser.close()
        logger.info(f"[enterprise] 共获取 {len(all_jobs)} 条")
        return all_jobs
