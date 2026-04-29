"""浏览器自动投递 (Selenium)"""
import json
import time
from pathlib import Path
from typing import Optional, Callable

from backend.core.config import Config, DATA_DIR
from backend.utils.logger import logger

try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

COOKIE_DIR = DATA_DIR / "cookies"

PLATFORM_LOGIN = {
    "boss": {
        "home": "https://www.zhipin.com",
        "login_url": "https://www.zhipin.com/web/user/",
        "success_check": lambda src: any(k in src for k in ["我的BOSS", "个人中心", "退出登录", "logout"]),
    },
    "wuyou": {
        "home": "https://www.51job.com",
        "login_url": "https://login.51job.com/login.php",
        "success_check": lambda src: any(k in src for k in ["退出登录", "我的简历", "个人中心", "logout"]),
    },
}


def _cookie_file(platform: str) -> Path:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    return COOKIE_DIR / f"{platform}_cookies.json"


def save_cookies(driver, platform: str):
    with open(_cookie_file(platform), "w", encoding="utf-8") as f:
        json.dump(driver.get_cookies(), f, ensure_ascii=False)


def load_cookies(driver, platform: str) -> bool:
    f = _cookie_file(platform)
    if not f.exists():
        return False
    try:
        with open(f, encoding="utf-8") as fp:
            cookies = json.load(fp)
        for c in cookies:
            c.pop("sameSite", None)
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        driver.refresh()
        time.sleep(2)
        return True
    except Exception:
        return False


def has_cookies(platform: str) -> bool:
    return _cookie_file(platform).exists()


def clear_cookies(platform: str):
    f = _cookie_file(platform)
    if f.exists():
        f.unlink()


def get_stealth_driver(config: Config, headless: bool = False):
    if not SELENIUM_AVAILABLE:
        raise RuntimeError("Selenium 未安装，请运行: pip install selenium")
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = uc.Chrome(options=options)
    return driver


class BrowserApplicator:
    def __init__(self, config: Config):
        if not SELENIUM_AVAILABLE:
            raise RuntimeError(
                "Selenium 未安装。请运行: pip install selenium undetected-chromedriver\n"
                "并安装 Chrome 浏览器"
            )
        self.config = config
        self._driver = None

    def __enter__(self):
        self._driver = get_stealth_driver(self.config, headless=False)
        return self

    def __exit__(self, *_):
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

    def login_and_apply(self, job: dict, on_status: Optional[Callable[[str], None]] = None,
                        qr_timeout: int = 120) -> dict:
        platform = job.get("platform", "boss")
        plat_cfg = PLATFORM_LOGIN.get(platform)
        if not plat_cfg:
            return {"success": False, "message": f"暂不支持平台: {platform}"}

        def _notify(msg):
            logger.info(msg)
            if on_status:
                on_status(msg)

        self._driver.get(plat_cfg["home"])
        time.sleep(1)
        if has_cookies(platform):
            load_cookies(self._driver, platform)
            if plat_cfg["success_check"](self._driver.page_source):
                _notify(f"[{platform}] Cookie 有效，已恢复登录态")
            else:
                clear_cookies(platform)
                ok = self._do_qr_login(platform, plat_cfg, qr_timeout, _notify)
                if not ok:
                    return {"success": False, "message": "扫码登录超时"}
        else:
            ok = self._do_qr_login(platform, plat_cfg, qr_timeout, _notify)
            if not ok:
                return {"success": False, "message": "扫码登录超时（2分钟内未完成）"}

        _notify("登录成功，正在投递...")
        if platform == "boss":
            return self._apply_boss(job, _notify)
        if platform == "wuyou":
            return self._apply_wuyou(job, _notify)
        return {"success": False, "message": f"投递逻辑暂未实现: {platform}"}

    def _do_qr_login(self, platform, plat_cfg, timeout, notify) -> bool:
        self._driver.get(plat_cfg["login_url"])
        notify(f"请在弹出的浏览器窗口中完成扫码登录（最多 {timeout} 秒）...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(2)
            if plat_cfg["success_check"](self._driver.page_source):
                save_cookies(self._driver, platform)
                notify("✅ 扫码登录成功")
                return True
        return False

    def _apply_boss(self, job: dict, notify) -> dict:
        url = job.get("url", "")
        if not url:
            return {"success": False, "message": "岗位 URL 为空"}
        self._driver.get(url)
        time.sleep(3)
        for sel in [".btn-startchat", ".op-btn-chat", "[class*='startchat']"]:
            try:
                btn = WebDriverWait(self._driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                notify(f"已点击「立即沟通」: {job.get('title')} @ {job.get('company')}")
                time.sleep(2)
                return {"success": True, "message": "投递成功"}
            except TimeoutException:
                continue
        return {"success": False, "message": "未找到投递按钮"}

    def _apply_wuyou(self, job: dict, notify) -> dict:
        url = job.get("url", "")
        if not url:
            return {"success": False, "message": "岗位 URL 为空"}
        self._driver.get(url)
        time.sleep(3)
        for sel in ["a#app_ck", "a.but_sq", "button.btn.apply", "div.apply-btn"]:
            try:
                btn = WebDriverWait(self._driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                )
                btn.click()
                notify(f"已点击投递: {job.get('title')} @ {job.get('company')}")
                time.sleep(2)
                return {"success": True, "message": "投递成功"}
            except TimeoutException:
                continue
        return {"success": False, "message": "未找到投递按钮"}
