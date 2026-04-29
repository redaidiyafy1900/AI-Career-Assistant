"""自定义异常"""


class ResumeParseError(Exception):
    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"简历解析失败 [{file_path}]: {reason}")


class ApplicationError(Exception):
    def __init__(self, job_id: str, method: str, reason: str):
        self.job_id = job_id
        self.method = method
        self.reason = reason
        super().__init__(f"投递失败 [job={job_id}, method={method}]: {reason}")


class ScraperError(Exception):
    def __init__(self, platform: str, reason: str):
        self.platform = platform
        self.reason = reason
        super().__init__(f"采集失败 [{platform}]: {reason}")
