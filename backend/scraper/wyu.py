"""五邑大学官网岗位爬虫"""
import re
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


class WyuScraper(BaseScraper):
    """五邑大学官网岗位爬虫"""
    platform = "wyu"

    def __init__(self, config: Config):
        super().__init__(config)
        self.base_url = "https://www.wyu.edu.cn"

    def scrape(self, keyword: str, city: str = "江门", max_pages: int = 3) -> List[dict]:
        """采集五邑大学官网岗位信息"""
        check_playwright()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._run_in_thread, keyword, city, max_pages)
            return future.result()

    def _run_in_thread(self, keyword, city, max_pages):
        """在独立线程中运行异步爬虫"""
        import sys
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._async_scrape(keyword, city, max_pages))
        finally:
            loop.close()

    async def _async_scrape(self, keyword: str, city: str, max_pages: int) -> List[dict]:
        """异步采集五邑大学岗位"""
        from playwright.async_api import async_playwright
        logger.info(f"[五邑大学官网] 开始: keyword={keyword}, city={city}")

        all_jobs = []

        # 五邑大学官网可能的招聘页面URL
        search_urls = [
            f"{self.base_url}/rczp.htm",  # 人才招聘主页
            f"{self.base_url}/xwwz.htm",  # 校务咨询
            f"{self.base_url}/zpxx.htm",  # 招聘信息
        ]

        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()

            for url in search_urls:
                try:
                    logger.info(f"[五邑大学官网] 访问: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await asyncio.sleep(random.uniform(2.0, 4.0))

                    # 查找岗位列表项（根据实际网站结构调整）
                    # 尝试多种可能的CSS选择器
                    possible_selectors = [
                        ".news-list li",  # 常见新闻列表
                        ".article-list li",
                        ".list-item",
                        ".content-list li",
                        "ul li",  # 通用列表
                    ]

                    items = []
                    for selector in possible_selectors:
                        items = await page.query_selector_all(selector)
                        if items and len(items) > 0:
                            logger.info(f"[五邑大学官网] 找到 {len(items)} 条记录（选择器: {selector}）")
                            break

                    # 如果没有找到列表项，尝试查找所有链接
                    if not items or len(items) == 0:
                        logger.info("[五邑大学官网] 未找到列表项，尝试查找所有链接")
                        all_links = await page.query_selector_all("a[href]")
                        for link in all_links[:50]:  # 限制前50个链接
                            text = clean_text(await link.inner_text())
                            href = await link.get_attribute("href") or ""

                            # 筛选包含招聘关键词的链接
                            if any(kw in text.lower() for kw in ['招聘', '岗位', '职位', '招', '招人', '招工']):
                                try:
                                    title = text.strip()
                                    if not title or len(title) < 4:
                                        continue

                                    # 构造完整URL
                                    if href.startswith("/"):
                                        href = self.base_url + href
                                    elif not href.startswith("http"):
                                        href = self.base_url + "/" + href

                                    job_id = hashlib.md5((self.platform + title).encode()).hexdigest()

                                    # 获取岗位详情
                                    description = ""
                                    try:
                                        await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                                        await asyncio.sleep(random.uniform(1.5, 3.0))

                                        # 尝试多种详情页选择器
                                        content_selectors = [
                                            ".article-content",
                                            ".content",
                                            ".news-content",
                                            ".detail-content",
                                            "article",
                                            "#content",
                                            ".main-content",
                                        ]

                                        for sel in content_selectors:
                                            content_el = await page.query_selector(sel)
                                            if content_el:
                                                text = clean_text(await content_el.inner_text())
                                                if len(text) >= 50:
                                                    description = text[:5000]
                                                    logger.info(f"[五邑大学官网] 获取详情成功，长度: {len(description)}")
                                                    break
                                    except Exception as e:
                                        logger.debug(f"[五邑大学官网] 获取详情失败: {e}")

                                    # 添加到结果
                                    all_jobs.append(self._normalize_job({
                                        "platform": self.platform,
                                        "job_id": job_id,
                                        "title": title,
                                        "company": "五邑大学",
                                        "city": city,
                                        "district": "蓬江区",
                                        "education": "本科及以上",
                                        "experience": "不限",
                                        "industry": "教育",
                                        "description": description,
                                        "url": href,
                                        "scraped_at": now_iso(),
                                    }, self.platform))

                                    # 返回列表页
                                    try:
                                        await page.go_back()
                                        await asyncio.sleep(random.uniform(1.0, 2.0))
                                    except:
                                        pass

                                except Exception as e:
                                    logger.debug(f"[五邑大学官网] 处理链接异常: {e}")

                    else:
                        # 处理找到的列表项
                        for item in items[:30]:  # 限制处理数量
                            try:
                                # 尝试获取标题和链接
                                title_el = await item.query_selector("a")
                                if title_el:
                                    title = clean_text(await title_el.inner_text())
                                    href = await title_el.get_attribute("href") or ""
                                else:
                                    title = clean_text(await item.inner_text())
                                    href = ""

                                if not title or len(title) < 4:
                                    continue

                                # 构造完整URL
                                if href.startswith("/"):
                                    href = self.base_url + href
                                elif not href.startswith("http"):
                                    href = self.base_url + "/" + href

                                # 过滤：只保留包含关键词或招聘相关的内容
                                if keyword.lower() not in title.lower() and \
                                   not any(kw in title for kw in ['招聘', '岗位', '职位', '招']):
                                    continue

                                job_id = hashlib.md5((self.platform + title).encode()).hexdigest()

                                # 获取岗位详情
                                description = ""
                                if href and href.startswith("http"):
                                    try:
                                        await page.goto(href, wait_until="domcontentloaded", timeout=20000)
                                        await asyncio.sleep(random.uniform(1.5, 3.0))

                                        content_selectors = [
                                            ".article-content",
                                            ".content",
                                            ".news-content",
                                            ".detail-content",
                                            "article",
                                            "#content",
                                        ]

                                        for sel in content_selectors:
                                            content_el = await page.query_selector(sel)
                                            if content_el:
                                                text = clean_text(await content_el.inner_text())
                                                if len(text) >= 50:
                                                    description = text[:5000]
                                                    break
                                        await page.go_back()
                                        await asyncio.sleep(random.uniform(1.0, 2.0))
                                    except Exception as e:
                                        logger.debug(f"[五邑大学官网] 获取详情失败: {e}")

                                all_jobs.append(self._normalize_job({
                                    "platform": self.platform,
                                    "job_id": job_id,
                                    "title": title,
                                    "company": "五邑大学",
                                    "city": city,
                                    "district": "蓬江区",
                                    "education": "本科及以上",
                                    "experience": "不限",
                                    "industry": "教育",
                                    "description": description,
                                    "url": href,
                                    "scraped_at": now_iso(),
                                }, self.platform))

                            except Exception as e:
                                logger.debug(f"[五邑大学官网] 解析异常: {e}")

                except Exception as e:
                    logger.warning(f"[五邑大学官网] 访问失败: {e}")

                await asyncio.sleep(random.uniform(2.0, 4.0))

            await browser.close()

        logger.info(f"[五邑大学官网] 共获取 {len(all_jobs)} 条岗位")
        return all_jobs
