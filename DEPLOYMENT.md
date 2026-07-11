# ScholarLint — 部署交接文档

> 适用对象：接手本地部署的同事  
> 系统版本：v5.4.1  
> 最后更新：2026-07-11

---

## 1. 系统概述

**ScholarLint**（投稿通）是一个 LaTeX 学术论文投稿前完整性检测系统，支持：

| Gate | 检测内容 |
|------|---------|
| Data Integrity | 正文数字声明 vs 表格数据一致性（NCG 算法） |
| Citation Consistency | `\cite{}` key 是否在 `.bib` 中定义 |
| Figure/Table Cross-ref | `\ref{}` 是否有对应 `\label{}` |
| Reference Authenticity | DOI 有效性、标题/作者与 Crossref 比对 |
| Structure Integrity | 文件结构、图片路径、bib 链接 |
| Writing Quality | AI 痕迹检测、匿名化检查、写作质量 |

---

## 2. 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12 | 推荐 3.12，不兼容 3.13+ |
| FastAPI | ≥0.100 | HTTP 框架 |
| SQLite | — | 任务状态存储（单文件 DB） |
| Crossref API | — | Reference gate DOI 验证 |
| LLM（可选） | — | NCG claim 提取，不配置则 fallback 到 regex |

---

## 3. 目录结构

```
integrity-assurance/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置读取（从 .env 或 data/secrets.enc）
│   ├── checks/              # 6 个 gate 实现
│   ├── parsers/             # LaTeX/bib/zip 解析器
│   ├── templates/index.html # 前端单页应用
│   └── static/              # 静态资源
├── data/                    # 运行时数据（不入 git）
│   ├── integrity.db         # SQLite 数据库
│   └── jobs/                # 报告文件（加密存储）
├── uploads/                 # 用户上传临时目录（不入 git）
├── .env.example             # 环境变量模板
├── Dockerfile               # 容器构建文件
├── docker-compose.yml       # 本地开发用
├── docker-compose.prod.yml  # 生产覆盖配置
└── requirements.txt         # Python 依赖
```

---

## 4. 快速启动（本地开发）

### 4.1 直接运行（推荐，无需 Docker）

```bash
# 1. 进入项目目录
cd integrity-assurance

# 2. 安装依赖（推荐用 uv，也可用 pip）
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少设置：
#   APP_ENV=local
#   CROSSREF_EMAIL=你的邮箱（Crossref polite pool 要求）

# 4. 启动服务
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 访问 http://localhost:8000
```

### 4.2 Docker 启动

```bash
# 1. 配置 .env（同上）

# 2. 构建并启动
docker compose up --build -d

# 查看日志
docker compose logs -f

# 停止
docker compose down
```

---

## 5. 环境变量说明

复制 `.env.example` 为 `.env`，按需填写：

```ini
# 运行环境（local / production）
APP_ENV=local

# LLM 配置（可选，用于 Data Integrity Gate 的 claim 提取）
# 不填则自动 fallback 到 regex 模式，precision 略降但完全可用
LLM_API_KEY=sk-xxx
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# Crossref polite pool（必填，否则 reference gate 很慢）
CROSSREF_EMAIL=yourname@example.com

# 以下留空即可，系统自动生成
JWT_SECRET=
ADMIN_KEY=

# 支付相关（demo 不需要）
PAYMENT_SANDBOX=true
ALIPAY_APP_ID=
ALIPAY_PRIVATE_KEY=
ALIPAY_PUBLIC_KEY=
```

> **重要**：`.env` 已在 `.gitignore` 中，**不会入 git**。切勿手动 `git add .env`。

---

## 6. LLM 配置说明

系统设计原则：**LLM 只用于理解（claim 提取），不用于判断（验证）**。

- **不配置 LLM**：完全 rule-based，Data Integrity Gate F1 ≈ 0.75，其余 gate F1 = 1.00
- **配置 LLM**：Data Integrity Gate F1 ≈ 0.93，接近 Claude-opus-4.7 standalone

支持任何 OpenAI-compatible API（OpenAI / Azure / 内部 LiteLLM proxy）。

---

## 7. 性能说明

| 操作 | 耗时 | 主要瓶颈 |
|------|------|---------|
| 上传 + 前5个 gate | < 2s | CPU/IO |
| Reference Authenticity Gate | 3–15s | Crossref API 网络 |
| 含 LLM claim 提取 | +1–3s | LLM API 调用 |

**Reference gate 优化参数**（`app/checks/gate_references.py`）：
```python
MAX_CONCURRENT = 10   # Crossref 并发请求数
TIMEOUT = 6.0         # 单次请求超时（秒）
```
如果 Crossref 访问不稳定，可调低 `MAX_CONCURRENT = 5`，调高 `TIMEOUT = 10.0`。

---

## 8. 数据安全

- 用户上传的 `.zip` 在检查完成后**立即删除**（`finally: shutil.rmtree`）
- 报告以 AES 加密存储在 `data/jobs/`
- 生产环境下报告按 owner（session cookie）隔离，非 owner 无法访问
- **不存储用户论文内容**，只存储报告 JSON

---

## 9. 生产部署（服务器）

```bash
# 1. 克隆代码
git clone <repo_url> /srv/scholarlint
cd /srv/scholarlint

# 2. 配置生产环境变量
cp .env.example .env
vim .env  # 设置 APP_ENV=production, CROSSREF_EMAIL, LLM_* 等

# 3. 创建数据目录（生产用独立路径，防系统盘满）
mkdir -p /srv/scholarlint/data /srv/scholarlint/uploads

# 4. 启动（生产配置）
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# 5. 配置 Nginx 反向代理（建议）
# 见下方 Nginx 配置示例
```

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 50M;  # 允许上传大 ZIP

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 120s;  # Reference gate 可能耗时较长
    }
}
```

---

## 10. 常见问题

### Q: Reference gate 太慢（>30s）
调低并发或检查服务器到 `api.crossref.org` 的网络连通性：
```bash
curl -I https://api.crossref.org/works/10.18653/v1/2020.acl-main.703
```

### Q: 上传后一直转圈不返回结果
检查 `uploads/` 目录权限，Docker 环境下确认 volume 挂载正确：
```bash
docker compose exec integrityguard ls /app/uploads/
```

### Q: `data/integrity.db` 报 SQLite locked
只能运行**一个** uvicorn worker（SQLite 不支持多进程写入）。不要加 `--workers 2`。

### Q: LLM 不生效（仍用 regex）
检查 `.env` 中 `LLM_API_KEY` 和 `LLM_BASE_URL` 是否正确。测试：
```bash
curl -s http://localhost:8000/api/health
# 返回 {"status":"ok","mode":"local"} 说明服务正常
# LLM 是否生效需看 gate_data.py 日志（设 LLM_API_KEY 后会有 LLM 请求日志）
```

### Q: 切换到 EN 模式部分文字仍显示中文
动态生成的 toast 消息和部分 JS 模板字符串尚未全部迁移到 i18n。静态 HTML 按钮已全部支持切换。后续可继续迁移 `app/templates/index.html` 中的 JS 字符串。

---

## 11. 代码关键位置

| 功能 | 文件 |
|------|------|
| 4 个核心 gate | `app/checks/gate_data.py`, `gate_citations.py`, `gate_figures.py`, `gate_references.py` |
| NCG 算法 | `app/checks/gate_data.py` → `_ncg_check()`, `_scope_sim()` |
| LLM claim 提取 | `app/checks/gate_data.py` → `_extract_claims_llm()` |
| API 路由 | `app/api/routes.py` |
| 前端单页应用 | `app/templates/index.html` |
| i18n 字典 | `index.html` 底部 `const I18N = {...}` |
| 配置 | `app/config.py` |

---

## 12. 实验数据位置

论文相关实验结果在：
```
research/bench/
├── benchmark_v3.json       # 226条测试用例
├── eval_results_v3.json    # Ours 系统评测结果
├── eval_llm_v3.json        # LLM baseline 结果
├── eval_report_v3.md       # 系统评测报告
└── eval_llm_v3.md          # 三系统对比报告（论文用）
```

---

## 13. 联系方式

项目负责人：Mengze Hong  
论文 repo：https://github.com/mengze-hong/ScholarLint-Paper  
Demo repo：https://github.com/mengze-hong/scholarlint-demo
