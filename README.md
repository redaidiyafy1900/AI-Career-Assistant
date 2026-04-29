# AI Career Assistant (智能职业发展助手)

> 基于 AI 的全流程职业发展服务平台 —— 岗位采集 / 简历管理 / 智能匹配 / 简历优化 / 自动投递 / 模拟面试

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

---

## 目录

- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [项目结构](#项目结构)
- [技术架构](#技术架构)
- [API 服务说明](#api-服务说明)
- [常见问题](#常见问题)

---

## 功能特性

| 模块 | 说明 |
|------|------|
| **岗位智能采集** | 支持实习僧、Boss直聘、智联招聘、前程无忧、五邑大学官网等 5 大平台 |
| **简历智能管理** | 上传 PDF/DOCX，AI 自动解析并提取关键信息 |
| **人岗智能匹配** | 基于大模型分析简历与岗位的多维度匹配度，可视化评分 |
| **简历智能优化** | 针对目标岗位自动生成优化建议和定制简历 |
| **自动投递** | SMTP 邮件自动化投递，进度追踪与统计 |
| **AI 模拟面试** | 文字面试 / 视频面试，实时对话式交互，AI 自动生成评估报告 |

---

## 快速开始

### 前提条件

- **Python 3.11+**
- **Windows 10+**（Linux/Mac 需手动调整部分路径）
- **网络连接稳定**（需调用 AI API）

### 第一步：克隆项目

```bash
git clone https://github.com/YOUR_USERNAME/ai-career-assistant.git
cd ai-career-assistant
```

### 第二步：安装依赖

**Windows 用户（双击运行）：**

```bash
setup.bat
```

或手动执行：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

> 推荐使用国内镜像源加速下载。

### 第三步：配置环境变量

```bash
# 复制配置模板
copy .env.example .env

# 编辑 .env 文件，填入你的 API 密钥
notepad .env
```

**必须配置的项：**

| 配置项 | 说明 | 获取方式 |
|--------|------|----------|
| `INTERVIEW_DOBAO_API_KEY` | 火山方舟(豆包) API Key | [火山引擎控制台](https://console.volcengine.com/ark/) |
| `INTERVIEW_DOBAO_MODEL` | 模型端点 ID（如 `ep-xxxxx`） | 同上 |
| `DOUBAO_API_KEY` | 豆包 API Key（同上即可） | 同上 |
| `DOUBAO_MODEL` | 豆包模型 ID（同上即可） | 同上 |

可选配置：

| 配置项 | 说明 |
|--------|------|
| `SMTP_HOST/PORT/EMAIL/PASSWORD` | 邮件投递功能（QQ邮箱） |
| `PORT` | 服务器端口（默认 `3002`） |

### 第四步：启动项目

**Windows 用户（双击运行）：**

```bash
start.bat
```

或手动执行：

```bash
python server.py
```

启动成功后浏览器将自动打开 `http://localhost:3002/index.html`

---

## 环境配置详解

### `.env` 完整示例

```env
# ==========================================
#  火山方舟（豆包）API - 当前使用的 AI 后端
# ==========================================

# 面试功能（文字面试 + 视频面试共用）
INTERVIEW_DOBAO_URL=https://ark.cn-beijing.volces.com/api/v3/chat/completions
INTERVIEW_DOBAO_API_KEY=your_api_key_here
INTERVIEW_DOBAO_MODEL=ep-your_model_id_here

# 岗位匹配 / 简历解析 / 优化
DOUBAO_API_KEY=your_api_key_here
DOUBAO_MODEL=ep-your_model_id_here

# ==========================================
#  FastGPT API - 原始实现（已弃用，保留供切换）
# ==========================================
# 面试功能最初基于 FastGPT 私有部署实现。
# 如有 FastGPT 服务，可取消注释以下配置切换回去：
#
# FASTGPT_BASE_URL=http://your-fastgpt-server:3000
# INTERVIEW_FASTGPT_API_KEY=your_key
# INTERVIEW_FASTGPT_APP_ID=your_app_id

# ==========================================
#  SMTP 邮件（自动投递，可选）
# ==========================================
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_EMAIL=your_email@qq.com
SMTP_PASSWORD=your_smtp_auth_code

# 服务器
PORT=3002
MAX_FILE_SIZE=5242880
```

---

## 项目结构

```
ai-career-assistant/
├── server.py                  # Flask 主入口（所有 API 路由）
├── start.bat                  # Windows 一键启动脚本
├── setup.bat                  # Windows 环境初始化脚本
├── run.bat                    # Windows 快速启动
├── index.html                 # 根目录重定向页
│
├── backend/                   # 后端核心模块
│   ├── scraper/               # 爬虫模块（5个平台）
│   │   ├── shixiseng.py       #   实习僧
│   │   ├── boss.py            #   Boss直聘
│   │   ├── zhilian.py         #   智联招聘
│   │   ├── wuyou.py           #   前程无忧
│   │   └── wyu.py             #   五邑大学官网
│   ├── storage/               # SQLite 数据库管理
│   ├── processor/             # 业务处理（匹配、优化等）
│   ├── resume/                # 简历处理（PDF/DOCX 解析、生成）
│   ├── applicator/            # 自动投递（SMTP邮件）
│   ├── core/                  # 核心配置（config.py）
│   └── utils/                 # 工具类（doubao_client, logger等）
│
├── frontend/                  # 前端页面
│   ├── index.html             #   主页
│   ├── job_scraper.html       #   岗位采集
│   ├── job_match.html         #   岗位匹配
│   ├── resume_optimize.html   #   简历优化
│   ├── interview_first.html   #   面试选择页
│   ├── interview_coach.html   #   文字面试
│   ├── interview_avatar.html  #   视频面试（3D头像）
│   ├── interview_choice.html  #   岗位选择
│   ├── interview_report.html  #   面试报告
│   ├── css/                   #   样式文件
│   ├── js/                    #   JavaScript 逻辑
│   ├── assets/                #   静态资源（3D模型、字体、视频）
│   └── data/                  #   示例数据（jobs.json）
│
├── data/                      # 运行时数据
│   ├── career.db              #   SQLite 数据库（自动创建）
│   ├── tailored/              #   生成的定制简历 PDF
│   ├── *.json / *.docx        #   配置和数据文件
│
├── screenshots/               # 项目截图
├── requirements.txt           # Python 依赖清单
├── .env.example               # 环境变量模板（复制为 .env 使用）
├── .gitignore                 # Git 忽略规则
└── DEPLOYMENT.md              # 部署文档
```

---

## 技术架构

### 前端技术栈

| 技术 | 用途 |
|------|------|
| HTML5 + CSS3 | 页面结构与样式 |
| JavaScript (ES6+) | 交互逻辑、API调用 |
| TailwindCSS | UI 样式框架 |
| Chart.js | 数据可视化图表 |
| Three.js (via GLB) | 3D 面试头像 |

### 后端技术栈

| 技术 | 用途 |
|------|------|
| Python 3.11+ | 核心语言 |
| Flask 3.0+ | Web 框架 + RESTful API |
| Flask-CORS | 跨域支持 |
| SQLite | 数据存储（轻量级，无需额外安装） |

### AI 服务

#### 当前方案：火山方舟 API（豆包）

本项目当前使用 **火山引擎方舟平台** 的豆包大模型作为统一 AI 后端：
- **模拟面试对话** — 多轮实时问答、追问、评分
- **面试报告生成** — 综合评估、优势提炼、改进建议
- **岗位匹配分析** — 简历与岗位多维度对比
- **简历解析与优化** — 关键信息提取、针对性润色
- **自动投递邮件** — AI 生成求职信内容

#### 原始方案：FastGPT（保留代码，可切换）

面试功能的**原始设计**基于 **FastGPT** 私有部署服务实现。相关代码仍保留在项目中，包括：
- `server.py` 中的 `call_fastgpt_interview()` 函数（FastGPT 调用逻辑）
- `.env.example` 中的 `FASTGPT_*` 配置项
- `backend/core/config.py` 中的 `fastgpt_base_url` 等字段

> **切换方法**：在 `.env` 中配置 `FASTGPT_BASE_URL`、`INTERVIEW_FASTGPT_API_KEY`、`INTERVIEW_FASTGPT_APP_ID`，并将 `server.py` 中的面试路由指向 FastGPT 调用函数即可。

### 爬虫技术

| 技术 | 用途 |
|------|------|
| Playwright | 现代化网页自动化（主要方案） |
| Selenium + undetected-chromedriver | 反检测浏览器自动化 |
| BeautifulSoup4 + lxml | HTML 解析与信息提取 |

---

## 常见问题

### Q1: 安装依赖时报错怎么办？

使用国内镜像源：

```bash
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

如果 Playwright 安装失败，单独执行：

```bash
playwright install chromium
```

### Q2: 启动后页面打不开？

1. 确认控制台没有报错
2. 检查端口是否被占用：`.env` 中修改 `PORT`
3. 手动访问：`http://localhost:3002/index.html`

### Q3: AI 功能不工作？

1. 确认 `.env` 已正确填写 API Key
2. 确认网络可以访问 `ark.cn-beijing.volces.com`
3. 查看控制台 `[API调用]` 相关日志确认请求状态
4. 检查 API Key 是否有效且有余额

### Q4: 如何切换回 FastGPT？

1. 在 `.env` 中取消注释 `FASTGPT_BASE_URL`、`INTERVIEW_FASTGPT_API_KEY`、`INTERVIEW_FASTGPT_APP_ID`
2. 填入你的 FastGPT 服务地址和密钥
3. 修改 `server.py` 中的面试路由，将调用从 `call_doubao_interview()` 切换为 `call_fastgpt_interview()`
4. 重启服务器

### Q5: 爬虫功能无法使用？

爬虫需要浏览器驱动支持：

```bash
# 安装 Playwright 浏览器
playwright install chromium

# 或确保 Chrome 已安装（Selenium 方案需要）
```

部分平台（Boss直聘）可能需要登录态 Cookie。

### Q6: 从 GitHub 克隆后数据库不存在？

首次启动时会**自动创建** SQLite 数据库 (`data/career.db`)，无需手动初始化。

---

## 更新日志

### v2.0.0 (2026-04-27)

- **重构**: AI 后端从 FastGPT 迁移至火山方舟(豆包) API
- **新增**: 面试报告自动生成（综合评分、优势提炼、改进建议）
- **新增**: 3D 头像视频面试功能
- **优化**: JSON 预处理容错机制，减少解析失败
- **清理**: 移除临时脚本和中间产物，精简项目结构

### v1.0.2 (2026-04-16)

- 新增一键启动脚本 (`start.bat`, `setup.bat`)
- 新增五邑大学官网岗位采集
- 完善项目文档

### v1.0.1 (2026-03-15)

- 新增自动投递功能（SMTP 邮件）
- 优化岗位匹配算法
- 新增数据分析功能

### v1.0.0 (2026-02-10)

- 项目初始发布
- 实现 6 大核心功能
- 集成 FastGPT + 豆包 双 AI 后端

---

## 许可证

[MIT License](LICENSE)

---

## 作者

智能职业发展助手团队

---

> **提示**: 首次使用请务必先复制 `.env.example` 为 `.env` 并填入 API 密钥。
