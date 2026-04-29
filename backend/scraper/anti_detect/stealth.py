"""通用 Playwright 爬虫工具 — 被各平台爬虫调用"""
import asyncio
import os
import sys
import re
import random
import hashlib
import urllib.parse
from typing import List

try:
    from playwright.async_api import async_playwright, TimeoutError as PwTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

CHROME_PATH = "C:/Program Files/Google/Chrome/Application/chrome.exe"

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}, app: {}};
"""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def check_playwright():
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError(
            "Playwright 未安装。请运行:\n"
            "pip install playwright\n"
            "playwright install chromium"
        )


def run_async(coro):
    """在新线程中运行异步任务，避免事件循环冲突"""
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_in_thread, coro)
        return future.result()


def _run_in_thread(coro):
    if sys.platform == "win32":
        loop = asyncio.ProactorEventLoop()
    else:
        loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def create_browser_context(playwright):
    chrome_path = CHROME_PATH if os.path.exists(CHROME_PATH) else None
    browser = await playwright.chromium.launch(
        executable_path=chrome_path,
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
              "--disable-dev-shm-usage", "--disable-gpu"],
    )
    context = await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1440, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
    )
    await context.add_init_script(STEALTH_SCRIPT)
    return browser, context


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"[\ue000-\uf8ff]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_salary(sal: str):
    if not sal:
        return None, None
    m = re.search(r"(\d+)[-~～](\d+)\s*元/天", sal)
    if m:
        return int(m.group(1)) * 22, int(m.group(2)) * 22
    m = re.search(r"(\d+)[-~～](\d+)\s*元/月", sal)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)[-~～](\d+)\s*[Kk]", sal)
    if m:
        return int(m.group(1)) * 1000, int(m.group(2)) * 1000
    m = re.search(r"(\d+)[^0-9]+(\d+)", sal)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return min(a, b), max(a, b)
    return None, None
