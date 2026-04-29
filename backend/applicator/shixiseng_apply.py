"""
实习僧批量自动投递模块 (Playwright)
重构版本：模块化、类型安全、支持生成器模式
"""
import json
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Callable, Generator, Literal

from backend.core.config import DATA_DIR
from backend.utils.logger import logger

try:
    from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# ============================================================================
# 配置层 (Config Layer)
# ============================================================================

@dataclass
class ShixisengApplyConfig:
    """实习僧投递配置"""
    # 文件路径
    cookie_path: Path = field(default_factory=lambda: DATA_DIR / "shixiseng_cookies.json")
    log_path: Path = field(default_factory=lambda: DATA_DIR / "shixiseng_apply_log.jsonl")
    
    # 基础URL
    base_url: str = "https://www.shixiseng.com"
    login_url: str = "https://www.shixiseng.com/login"
    
    # 重试与超时配置
    page_retry_times: int = 3
    login_timeout: int = 1800  # 30分钟
    goto_timeout: int = 30000
    selector_timeout: int = 10000
    confirm_timeout: int = 5000
    
    # 防检测延时配置
    delay_min: int = 10
    delay_max: int = 60
    
    # 浏览器配置
    headless: bool = False
    viewport: dict = field(default_factory=lambda: {"width": 1600, "height": 900})
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"
    
    # 投递按钮选择器（优先级从高到低）
    apply_btn_selectors: List[str] = field(default_factory=lambda: [
        "div.btn-box.resume_apply:has-text('投个简历')",
        "div:has-text('投个简历')",
        ".resume_apply",
        "div:has-text('立即申请')"
    ])
    
    # 确认按钮选择器
    confirm_selectors: List[str] = field(default_factory=lambda: [
        "div.btn:has-text('确认投递')",
        "div:has-text('确认投递')",
        "div:has-text('确认')"
    ])
    
    # 岗位关闭关键词
    closed_keywords: List[str] = field(default_factory=lambda: [
        "该职位已下线", "职位已关闭", "岗位已过期"
    ])
    
    # 已投递关键词
    applied_keywords: List[str] = field(default_factory=lambda: [
        "已投递", "已申请"
    ])


# ============================================================================
# 数据模型层 (Data Modeling)
# ============================================================================

class ApplyStatus:
    """投递状态枚举"""
    SUCCESS = "success"
    FAILED = "failed"
    CLOSED = "closed"
    SKIPPED = "skipped"
    PENDING = "pending"


class ApplyResult(dict):
    """投递结果数据类"""
    def __init__(
        self,
        url: str,
        status: str,
        message: str = "",
        applied_at: Optional[str] = None,
        retry_count: int = 0,
        job_title: str = ""
    ):
        super().__init__()
        self["url"] = url
        self["status"] = status
        self["message"] = message
        self["applied_at"] = applied_at or datetime.now().isoformat()
        self["retry_count"] = retry_count
        self["job_title"] = job_title
    
    @property
    def url(self) -> str:
        return self["url"]
    
    @property
    def status(self) -> str:
        return self["status"]
    
    @property
    def message(self) -> str:
        return self["message"]
    
    @property
    def applied_at(self) -> str:
        return self["applied_at"]
    
    @property
    def retry_count(self) -> int:
        return self["retry_count"]
    
    def is_success(self) -> bool:
        return self.status == ApplyStatus.SUCCESS


class BatchProgress:
    """批量投递进度"""
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.success = 0
        self.failed = 0
        self.closed = 0
        self.skipped = 0
    
    def update(self, result: ApplyResult):
        self.current += 1
        if result.is_success():
            self.success += 1
        elif result.status == ApplyStatus.FAILED:
            self.failed += 1
        elif result.status == ApplyStatus.CLOSED:
            self.closed += 1
        elif result.status == ApplyStatus.SKIPPED:
            self.skipped += 1
    
    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "current": self.current,
            "success": self.success,
            "failed": self.failed,
            "closed": self.closed,
            "skipped": self.skipped,
            "progress_percent": round(self.current / self.total * 100, 1) if self.total > 0 else 0
        }


# ============================================================================
# 核心逻辑层 (Core Logic Layer)
# ============================================================================

class ShixisengAutoApply:
    """
    实习僧批量投递器
    
    Features:
    - 配置化：将 Selectors/Paths/Timeouts 抽离为 ShixisengApplyConfig
    - 类型安全：ApplyResult/ApplyStatus 提供类型提示
    - 生成器模式：batch_apply_yield 支持实时进度回调
    - 上下文管理：__enter__/__exit__ 自动释放资源
    - 状态机抽象：登录流程封装为 ensure_login
    """
    
    def __init__(self, config: Optional[ShixisengApplyConfig] = None):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright 未安装。请运行:\n"
                "pip install playwright\n"
                "playwright install chromium"
            )
        
        self.config = config or ShixisengApplyConfig()
        
        # 内部状态
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._playwright = None
        
        # 回调函数
        self._on_progress: Optional[Callable[[ApplyResult, BatchProgress], None]] = None
        self._on_result: Optional[Callable[[ApplyResult], None]] = None
    
    # ========================================================================
    # 上下文管理器支持
    # ========================================================================
    
    def __enter__(self) -> "ShixisengAutoApply":
        self.init_browser()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.cleanup()
        return False
    
    # ========================================================================
    # 资源管理
    # ========================================================================
    
    def init_browser(self):
        """初始化浏览器"""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.config.headless,
            args=["--no-sandbox", "--start-maximized", "--no-proxy-server"]
        )
        self._context = self._browser.new_context(
            viewport=self.config.viewport,
            locale=self.config.locale,
            timezone_id=self.config.timezone,
        )
        
        # 注入反检测脚本
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        
        # 加载 Cookie
        self._load_cookies()
        
        # 创建新页面
        self._page = self._context.new_page()
        logger.info("浏览器初始化完成")
    
    def cleanup(self):
        """清理资源"""
        if self._page:
            try:
                self._save_cookies()
                self._page.close()
            except Exception:
                pass
            finally:
                self._page = None
        
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            finally:
                self._browser = None
        
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            finally:
                self._playwright = None
        
        logger.info("浏览器资源已释放")
    
    def clear_cookies(self):
        """清除 Cookie"""
        try:
            self.config.cookie_path.unlink(missing_ok=True)
            logger.info("Cookie 已清除")
        except Exception as e:
            logger.warning(f"清除 Cookie 失败: {e}")
    
    # ========================================================================
    # Cookie 管理
    # ========================================================================
    
    def _load_cookies(self):
        """加载 Cookie"""
        if not self.config.cookie_path.exists():
            return
        
        try:
            cookies = json.loads(self.config.cookie_path.read_text(encoding="utf-8"))
            self._context.add_cookies(cookies)
            logger.info(f"已加载 {len(cookies)} 个 Cookie")
        except Exception as e:
            logger.warning(f"加载 Cookie 失败: {e}")
    
    def _save_cookies(self):
        """保存 Cookie"""
        if not self._context:
            return
        
        try:
            cookies = self._context.cookies()
            self.config.cookie_path.parent.mkdir(parents=True, exist_ok=True)
            self.config.cookie_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            logger.info(f"已保存 {len(cookies)} 个 Cookie")
        except Exception as e:
            logger.warning(f"保存 Cookie 失败: {e}")
    
    # ========================================================================
    # 登录状态管理
    # ========================================================================
    
    def _check_session_valid(self) -> bool:
        """检查会话是否有效"""
        try:
            self._page.goto(self.config.base_url, timeout=self.config.goto_timeout)
            time.sleep(1)
            is_logged = "/login" not in self._page.url
            logger.info(f"会话检查: {'有效' if is_logged else '无效'}")
            return is_logged
        except Exception as e:
            logger.warning(f"会话检查失败: {e}")
            return False
    
    def _perform_manual_login(self):
        """执行手动登录流程"""
        self.clear_cookies()
        self._page.goto(self.config.login_url, timeout=self.config.goto_timeout)
        
        deadline = time.time() + self.config.login_timeout
        while time.time() < deadline:
            if "/login" not in self._page.url:
                self._save_cookies()
                logger.info("登录成功！Cookie 已保存")
                return
            time.sleep(1)
        
        raise TimeoutError("登录超时，请重新运行程序")
    
    def ensure_login(self):
        """
        确保处于登录状态
        
        状态机逻辑:
        1. 检查会话有效性
        2. 若无效，触发手动登录
        3. 保存 Cookie
        """
        if self._check_session_valid():
            logger.info("会话有效，跳过登录")
            return
        
        logger.warning("会话无效，开始手动登录流程")
        self._perform_manual_login()
    
    # ========================================================================
    # 原子操作方法 (Atomic Methods)
    # ========================================================================
    
    def _navigate_to_job(self, url: str, retry_times: int = None) -> bool:
        """
        导航到岗位页面
        
        Returns:
            bool: 导航是否成功
        """
        retry_times = retry_times or self.config.page_retry_times
        
        for attempt in range(retry_times):
            try:
                # 使用更宽松的等待策略，避免 networkidle 超时
                # "domcontentloaded" 比 "networkidle" 更可靠
                self._page.goto(url, timeout=self.config.goto_timeout, wait_until="domcontentloaded")
                
                # 等待页面基本加载完成（适应实习僧的动态加载）
                time.sleep(3)
                
                # 检查页面标题，确认不是404或其他错误页
                if "404" not in self._page.title() and "页面不存在" not in self._page.content():
                    logger.debug(f"导航成功 (尝试 {attempt + 1}/{retry_times})")
                    return True
                    
            except Exception as e:
                logger.warning(f"导航失败 (尝试 {attempt + 1}/{retry_times}): {e}")
                time.sleep(2)
        
        return False
    
    def _detect_job_status(self) -> str:
        """
        检测岗位状态
        
        Returns:
            str: 状态类型 (ready/closed/applied)
        """
        content = self._page.content()
        
        # 检查是否已关闭
        for kw in self.config.closed_keywords:
            if kw in content:
                logger.info(f"检测到岗位已关闭: {kw}")
                return ApplyStatus.CLOSED
        
        # 检查是否已投递
        for kw in self.config.applied_keywords:
            if kw in content:
                logger.info(f"检测到已投递: {kw}")
                return ApplyStatus.SKIPPED
        
        return ApplyStatus.PENDING
    
    def _find_apply_button(self) -> Optional[object]:
        """
        查找投递按钮
        
        Returns:
            ElementHandle 或 None
        """
        for selector in self.config.apply_btn_selectors:
            try:
                btn = self._page.wait_for_selector(
                    selector,
                    timeout=self.config.selector_timeout,
                    state="visible"
                )
                if btn:
                    logger.debug(f"找到投递按钮: {selector}")
                    return btn
            except Exception:
                continue
        
        logger.warning("未找到投递按钮")
        return None
    
    def _click_apply_button(self, btn) -> bool:
        """
        点击投递按钮
        
        Returns:
            bool: 是否点击成功
        """
        try:
            btn.click(delay=200)
            time.sleep(2)
            logger.debug("投递按钮已点击")
            return True
        except Exception as e:
            logger.warning(f"点击投递按钮失败: {e}")
            return False
    
    def _find_and_click_confirm(self) -> bool:
        """
        查找并点击确认按钮
        
        Returns:
            bool: 是否找到并点击成功
        """
        for selector in self.config.confirm_selectors:
            try:
                confirm_btn = self._page.wait_for_selector(
                    selector,
                    timeout=self.config.confirm_timeout,
                    state="visible"
                )
                if confirm_btn:
                    confirm_btn.click(delay=200)
                    time.sleep(1)
                    logger.debug(f"确认按钮已点击: {selector}")
                    return True
            except Exception:
                continue
        
        logger.info("未找到确认按钮（可能无需确认）")
        return False
    
    def _build_result(
        self,
        url: str,
        status: str,
        message: str = "",
        retry_count: int = 0,
        job_title: str = ""
    ) -> ApplyResult:
        """构建投递结果"""
        # 尝试从当前页面提取岗位标题
        if not job_title and hasattr(self, '_page') and self._page:
            try:
                title_el = self._page.query_selector('h1, .job-name, .position-name, .job-title')
                if title_el:
                    job_title = title_el.inner_text().strip()[:50]
            except Exception:
                pass
        return ApplyResult(
            url=url,
            status=status,
            message=message,
            applied_at=datetime.now().isoformat(),
            retry_count=retry_count,
            job_title=job_title
        )
    
    def _random_delay(self):
        """随机延时防风控"""
        delay = random.uniform(self.config.delay_min, self.config.delay_max)
        logger.debug(f"延时 {delay:.1f} 秒")
        time.sleep(delay)
    
    # ========================================================================
    # 单条投递
    # ========================================================================
    
    def apply_job(self, url: str) -> ApplyResult:
        """
        单条岗位投递
        
        状态机流程:
        1. navigate_to_job -> 导航到岗位页
        2. detect_job_status -> 检测状态
        3. find_apply_button -> 查找按钮
        4. click_apply_button -> 点击投递
        5. find_and_click_confirm -> 确认
        
        Args:
            url: 岗位URL
            
        Returns:
            ApplyResult: 投递结果
        """
        logger.info(f"开始投递: {url}")
        
        # 1. 导航
        if not self._navigate_to_job(url):
            return self._build_result(url, ApplyStatus.FAILED, "页面访问失败")
        
        # 2. 状态检测
        status = self._detect_job_status()
        if status == ApplyStatus.CLOSED:
            return self._build_result(url, ApplyStatus.CLOSED, "岗位已关闭")
        if status == ApplyStatus.SKIPPED:
            return self._build_result(url, ApplyStatus.SKIPPED, "已投递")
        
        # 3. 查找投递按钮
        btn = self._find_apply_button()
        if not btn:
            return self._build_result(url, ApplyStatus.FAILED, "未找到投递按钮")
        
        # 4. 点击投递
        if not self._click_apply_button(btn):
            return self._build_result(url, ApplyStatus.FAILED, "点击投递按钮失败")
        
        # 5. 确认
        self._find_and_click_confirm()
        
        return self._build_result(url, ApplyStatus.SUCCESS, "投递成功")
    
    # ========================================================================
    # 批量投递 - 列表模式
    # ========================================================================
    
    def batch_apply(self, url_list: List[str]) -> List[ApplyResult]:
        """
        批量投递 (返回列表)
        
        Args:
            url_list: URL列表
            
        Returns:
            List[ApplyResult]: 所有投递结果
        """
        results = []
        for result in self.batch_apply_yield(url_list):
            results.append(result)
        return results
    
    # ========================================================================
    # 批量投递 - 生成器模式 (推荐)
    # ========================================================================
    
    def batch_apply_yield(
        self,
        url_list: List[str],
        on_progress: Optional[Callable[[ApplyResult, BatchProgress], None]] = None
    ) -> Generator[ApplyResult, None, None]:
        """
        批量投递 (生成器模式，支持实时进度回调)
        
        推荐用于 Streamlit/Gradio 等需要实时更新UI的场景
        
        Args:
            url_list: URL列表
            on_progress: 进度回调 (result, progress) => None
            
        Yields:
            ApplyResult: 单条投递结果
        """
        progress = BatchProgress(len(url_list))
        
        try:
            self.init_browser()
            self.ensure_login()
            
            for i, url in enumerate(url_list, 1):
                # 执行投递
                result = self.apply_job(url)
                progress.update(result)
                
                # 日志记录
                status_icon = {
                    ApplyStatus.SUCCESS: "V",
                    ApplyStatus.FAILED: "X",
                    ApplyStatus.CLOSED: "-",
                    ApplyStatus.SKIPPED: "="
                }.get(result.status, "?")
                
                logger.info(
                    f"[{status_icon}] {i}/{len(url_list)} | "
                    f"{result.status} | {result.message[:30]} | {url}"
                )
                
                # 持久化到日志文件
                self._append_to_log(result)
                
                # 回调
                if on_progress:
                    try:
                        on_progress(result, progress)
                    except Exception as e:
                        logger.warning(f"进度回调失败: {e}")
                
                # 延时
                if i < len(url_list):
                    self._random_delay()
                
                yield result
                
        finally:
            self.cleanup()
    
    def _append_to_log(self, result: ApplyResult):
        """追加结果到日志文件"""
        try:
            self.config.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"日志写入失败: {e}")
    
    # ========================================================================
    # 便捷方法
    # ========================================================================
    
    def apply_single(self, url: str) -> ApplyResult:
        """
        便捷方法：单条投递（自动管理浏览器生命周期）
        
        Args:
            url: 岗位URL
            
        Returns:
            ApplyResult: 投递结果
        """
        try:
            self.init_browser()
            self.ensure_login()
            return self.apply_job(url)
        finally:
            self.cleanup()
    
    def apply_batch_with_callback(
        self,
        url_list: List[str],
        on_result: Callable[[ApplyResult], None]
    ) -> List[ApplyResult]:
        """
        便捷方法：带回调的批量投递
        
        Args:
            url_list: URL列表
            on_result: 每条结果回调
            
        Returns:
            List[ApplyResult]: 所有结果
        """
        def _callback(result: ApplyResult, progress: BatchProgress):
            on_result(result)
        
        return list(self.batch_apply_yield(url_list, on_progress=_callback))
