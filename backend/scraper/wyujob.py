"""五邑大学就业信息网爬虫 - 最终版"""
import re
import sys
import hashlib
import random
import json
import asyncio
import urllib.parse
import concurrent.futures
from typing import List, Optional

from backend.core.config import Config
from backend.utils.logger import logger
from backend.utils.date_utils import now_iso
from backend.scraper.base import BaseScraper
from backend.scraper.anti_detect.stealth import (
    check_playwright, create_browser_context, clean_text
)


# 导航菜单关键词 - 用于过滤非岗位内容
NAV_KEYWORDS = [
    '首页', '返回', '关闭', '更多', '上一个', '下一个', '详细', '说明',
    '登录', '注册', '学校首页', '部门首页', '就业教育', '人社专区',
    '新闻公告', '招聘信息', '就业服务', '服务指南', '联系我们',
    '就业政策', '就业活动', '就业指导', '办事流程', '下载中心',
    '就业年报', '市直招聘', '就业新闻', '就业公告', '宣讲会', '双选会',
    '在线招聘', '正式岗位', '实习岗位', '学生登录', '单位登录',
    '学校简介', '部门概述', '蓬江区招聘', '江海区招聘', '新会区招聘',
    '台山市招聘', '开平市招聘', '鹤山市招聘', '恩平市招聘',
    '企业入口', '学生入口', '个人中心', '我的简历', '职位搜索',
    '招聘会', '活动预告', '公告通知', '就业咨询', '常见问题'
]

# 岗位详情URL关键词
JOB_DETAIL_KEYWORDS = ['detail/recruit', 'detail/job', '/recruit/', '/job/', 'position']


class WyuJobScraper(BaseScraper):
    """五邑大学就业信息网爬虫
    
    采集五邑大学就业指导与服务中心的招聘信息
    官网: https://career.wyu.edu.cn
    """
    platform = "wyujob"

    # 就业信息网URL
    BASE_URL = "https://career.wyu.edu.cn"

    def __init__(self, config: Config):
        super().__init__(config)

    def scrape(self, keyword: str, city: str = "江门", max_pages: int = 5) -> List[dict]:
        """采集五邑大学就业信息"""
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

    async def _async_scrape(self, keyword: str, city: str, max_pages: int) -> List[dict]:
        """异步采集"""
        from playwright.async_api import async_playwright, TimeoutError as PwTimeout
        logger.info(f"[五邑大学就业] 开始: keyword={keyword}, city={city}")

        all_jobs = []

        async with async_playwright() as p:
            browser, context = await create_browser_context(p)
            page = await context.new_page()

            try:
                # 访问岗位列表页
                jobs_url = f"{self.BASE_URL}/module/jobs?is_practice=0&menu_id=3136"
                if keyword:
                    jobs_url += f"&keyword={urllib.parse.quote(keyword)}"
                    
                logger.info(f"[五邑大学就业] 访问岗位列表页")
                await page.goto(jobs_url, wait_until="domcontentloaded", timeout=30000)
                
                # 多次等待，确保JavaScript加载完成
                for i in range(3):
                    await asyncio.sleep(2)
                    # 尝试等待页面稳定
                    try:
                        await page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass
                
                # 尝试点击"在线招聘"或"正式岗位"标签
                try:
                    tabs = await page.query_selector_all(".tab-item, .tab-btn, [class*='tab']")
                    for tab in tabs:
                        tab_text = await tab.inner_text()
                        if '在线招聘' in tab_text or '正式岗位' in tab_text:
                            await tab.click()
                            await asyncio.sleep(3)
                            break
                except:
                    pass
                
                # 获取岗位数据 - 只获取岗位详情链接
                all_jobs = await self._extract_job_details(page, keyword, city)
                
            except Exception as e:
                logger.warning(f"[五邑大学就业] 采集异常: {e}")

            await browser.close()

        logger.info(f"[五邑大学就业] 共获取 {len(all_jobs)} 条")
        return all_jobs

    async def _extract_job_details(self, page, keyword: str, city: str) -> List[dict]:
        """提取岗位详情链接"""
        jobs = []
        seen_urls = set()
        
        try:
            # 获取所有可能的岗位链接
            links = await page.query_selector_all("a[href]")
            
            for link in links:
                try:
                    href = await link.get_attribute("href") or ""
                    title = clean_text(await link.inner_text())
                    
                    # 必须包含岗位详情URL关键词
                    has_detail_keyword = any(kw in href for kw in JOB_DETAIL_KEYWORDS)
                    
                    if has_detail_keyword:
                        # 构造完整URL
                        if href.startswith("/"):
                            full_url = self.BASE_URL + href
                        elif not href.startswith("http"):
                            full_url = f"{self.BASE_URL}/{href}"
                        else:
                            full_url = href
                            
                        # 去重
                        if full_url in seen_urls:
                            continue
                        seen_urls.add(full_url)
                        
                        # 过滤导航
                        if any(nav in title for nav in NAV_KEYWORDS):
                            continue
                        
                        # 过滤空标题
                        if not title or len(title) < 4:
                            continue
                        
                        # 生成唯一ID
                        job_id = hashlib.md5((self.platform + title + full_url).encode()).hexdigest()
                        
                        # 尝试获取详情页的邮箱信息
                        contact_email = await self._fetch_contact_email(page, full_url)
                        
                        jobs.append(self._normalize_job({
                            "platform": self.platform,
                            "job_id": job_id,
                            "title": title,
                            "company": "五邑大学",
                            "city": city,
                            "district": "蓬江区",
                            "education": "本科及以上",
                            "experience": "不限",
                            "industry": "教育",
                            "description": "",
                            "url": full_url,
                            "contact_email": contact_email,
                            "scraped_at": now_iso(),
                        }, self.platform))
                        
                except Exception as e:
                    continue
                    
            if jobs:
                logger.info(f"[五邑大学就业] 提取 {len(jobs)} 个岗位详情")
                    
        except Exception as e:
            logger.debug(f"[五邑大学就业] 提取详情失败: {e}")
            
        return jobs

    async def _fetch_contact_email(self, page, detail_url: str) -> str:
        """获取职位详情页的联系方式邮箱"""
        try:
            # 在当前页面查找邮箱（如果已经打开了详情页）
            page_text = await page.evaluate(
                "() => { const clone = document.body.cloneNode(true); "
                "['script','style','nav','header','footer','aside'].forEach(t => "
                "clone.querySelectorAll(t).forEach(e => e.remove())); return clone.innerText; }"
            )
            email = self._extract_email_from_text(page_text)
            if email:
                logger.info(f"[五邑大学就业] 找到邮箱: {email}")
                return email
            
            # 如果当前页面没有邮箱，尝试打开详情页
            try:
                await page.goto(detail_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(1.5)
                
                # 查找邮箱
                page_text = await page.evaluate(
                    "() => { const clone = document.body.cloneNode(true); "
                    "['script','style','nav','header','footer','aside'].forEach(t => "
                    "clone.querySelectorAll(t).forEach(e => e.remove())); return clone.innerText; }"
                )
                email = self._extract_email_from_text(page_text)
                if email:
                    logger.info(f"[五邑大学就业] 详情页找到邮箱: {email}")
                    return email
                    
            except Exception as e:
                logger.debug(f"[五邑大学就业] 获取详情页邮箱失败: {e}")
                
        except Exception as e:
            logger.debug(f"[五邑大学就业] 邮箱提取异常: {e}")
            
        return ""
