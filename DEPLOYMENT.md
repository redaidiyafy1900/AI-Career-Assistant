# GitHub 部署指南

## 从 GitHub 克隆并启动

### 1. 克隆仓库

```bash
git clone https://github.com/YOUR_USERNAME/ai-career-assistant.git
cd ai-career-assistant
```

### 2. 安装依赖

**Windows：**
```bash
setup.bat
```

**Linux / macOS：**
```bash
chmod +x start.sh
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
playwright install chromium   # 爬虫功能需要浏览器
```

### 3. 配置环境变量

```bash
# 复制模板
cp .env.example .env    # Linux/Mac
copy .env.example .env  # Windows

# 编辑填入 API 密钥
nano .env               # Linux/Mac
notepad .env            # Windows
```

**必须配置（至少一项 AI 服务）：**

| 配置项 | 必需 | 说明 |
|--------|------|------|
| `INTERVIEW_DOBAO_API_KEY` | **是** | 火山方舟 API Key |
| `INTERVIEW_DOBAO_MODEL` | **是** | 模型端点 ID |
| `DOUBAO_API_KEY` | **是** | 豆包 API Key |
| `DOUBAO_MODEL` | **是** | 豆包模型 ID |

> API Key 获取地址：[火山引擎控制台](https://console.volcengine.com/ark/management/endpoint)

可选：
- `SMTP_*` — 自动邮件投递（需 QQ 邮箱授权码）
- `FASTGPT_*` — 原始 FastGPT 方案（可切换）

### 4. 启动

```bash
start.bat     # Windows
./start.sh    # Linux/Mac
# 或手动: python server.py
```

访问 http://localhost:3002

---

## 上传到 GitHub

### 检查清单

上传前确认：

- [x] `.env` 已在 `.gitignore` 中（**绝不上传真实密钥！**）
- [x] `.env.example` 已提交（供他人参考格式）
- [x] `.gitignore` 包含 `Lib/`, `Include/`, `Scripts/`（Python 运行时）
- [x] `requirements.txt` 完整
- [x] README.md 已更新

### 推送命令

```bash
cd /path/to/AI
git init                          # 如果还没有
git add .
git commit -m "feat: initial release"
git branch -M main
git remote add origin https://github.com/YOU/REPO.git
git push -u origin main
```

---

## 敏感信息保护

以下内容已被 `.gitignore` 排除，**不会**被提交：

| 文件/目录 | 原因 |
|-----------|------|
| `.env` | 含真实 API Key、SMTP 密码 |
| `.env.local` | 本地环境覆盖 |
| `Lib/`, `Include/, `Scripts/` | Python 嵌入运行时（~200MB） |
| `data/career.db` | SQLite 数据库 |
| `backend/uploads/*` | 用户上传的简历文件 |
| `*.db`, `*.sqlite` | 数据库文件 |
| `__pycache__/` | Python 字节码缓存 |
| `*.log` | 日志文件 |

---

## 常见问题

**Q: 克隆后缺少 Python 运行时？**

`Lib/`, `Include/`, `Scripts/` 是 Windows 嵌入式 Python 发行版。如果需要，重新安装 Python 3.11+ 即可。

**Q: 如何验证 .env 未被提交？**

```bash
git status          # 不应显示 .env
git ls-files .env    # 应无输出
```

**Q: 误提交了密钥怎么办？**

```bash
# 1. 立即从 Git 历史移除
git rm --cached .env
git commit -m "security: remove .env from tracking"

# 2. 去 API 控制台轮换（更换）密钥！
```
