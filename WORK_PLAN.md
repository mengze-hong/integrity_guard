# ScholarLint 工作计划

> 这份是**接下来要做什么**的执行清单——按优先级排序，每条都可在一轮内完成、可独立 commit、零回归。
>
> 与 [TODO.md](TODO.md)（历史完成情况快照）和 [HANDOVER.md](HANDOVER.md)（项目状态总览）配合使用。
>
> **当前版本**：v5.3.90 · **当前节奏**：每轮一项，走完整流水线（验证 → CHANGELOG → commit → push）。

---

## 🔴 P0 — 安全基线（公网上线前必须完成）

### S1. 收紧无 owner 的 legacy job 在生产环境的访问

- **现状**：`_owner_metadata_allows()` 对没有 owner_type/owner_id 的报告默认放行（本地 demo 兼容）。生产环境这是过宽的旁路。
- **要做**：当 `settings.app_env in {"prod", "production"}` 时，缺少 owner metadata 的 job 视为不可访问。本地保持原行为。
- **验证**：新增测试覆盖 prod 模式下 legacy job 返回 403、本地仍可访问。
- **文件**：`app/api/routes.py` 的 `_owner_metadata_allows`、新增 `tests/test_legacy_owner_strict.py`。

### S2. API Token 真正接入鉴权

- **现状**：Pro/Team 用户能创建/撤销 API Token，但业务接口实际只认 cookie/JWT，token 还没生效。
- **要做**：扩展 `app/dependencies.py`：在 `get_current_user_optional` 里识别 `Authorization: Bearer <token>` 是否为有效的 API Token（按 SHA-256 哈希查 `api_tokens` 表），命中则返回对应用户。
- **验证**：新增测试覆盖 token 命中 / 错误 / 已撤销 / 跨用户拒绝。
- **文件**：`app/dependencies.py`、`app/auth.py` 或新增 `app/services/api_tokens.py`、`tests/test_api_token_auth.py`。

### S3. 全局脱敏覆盖更多敏感模式 ✅ v5.3.90

- ~~**现状**：`secrets_manager.redact()` 主要覆盖 LLM key/url。~~
- **已完成**：扩展规则覆盖 JWT、Bearer token、PEM 块、API token 前缀；`_SENSITIVE_NAMES` 加入 JWT_SECRET / ADMIN_KEY / ALIPAY_*；新增 `tests/test_redact.py` 8 项断言每种模式被替换且正常文本不误伤。

### S4. 匿名 sl_session cookie 的 secure 行为对齐

- **现状**：登录 cookie 在 HTTPS/生产下会自动 `Secure`，匿名 `sl_session` 没对齐。
- **要做**：在 `_get_request_owner` 写 cookie 处也按 `app_env`/HTTPS 设置 `secure`。
- **验证**：测试断言生产配置下匿名 cookie 也带 Secure。

---

## 🟡 P1 — 工程可维护性（继续"好交接给工程师"方向）

### M1. 拆分 routes.py：抽出 file_routes.py

- **范围**：把 `GET /api/files/{job_id}`、`GET /api/files/{job_id}/{file_path}`、`PUT /api/files/{job_id}/{file_path}`、`GET /api/download/{job_id}` 4 个端点迁到新模块。
- **要点**：保留外部 URL 不变；`main.py` 里挂载新 router；老 routes.py 留兼容 import 直到下一轮拆完。
- **验证**：现有 103+ 测试全过；URL 不变意味着前端无改动。

### M2. 拆分 routes.py：抽出 tool_routes.py

- **范围**：`/api/bib-clean`、`/api/tidyup`（GET+POST）、`/api/format-normalize`、`/api/fetch-bib`。
- **同 M1 节奏**：迁路由 + 挂载 + 测试不变。

### M3. 拆分 routes.py：抽出 checklist_routes.py

- **范围**：`/api/venue-checklist/{job_id}`。
- **小步**：作为 M1/M2 之后的延续。

### M4. 解耦 ai_routes.py 对 routes.py 私有 helper 的 import

- **现状**：`app/api/ai_routes.py` 仍 import `routes` 里的若干私有函数。
- **要做**：把通用 helper（`_get_report`、`_require_job_access`、`_extract_owner_metadata` 等）抽到 `app/services/permissions.py` 或 `app/services/jobs.py`，两个 router 都用 service。

### M5. 给 routes.py 未拆分区段加分段注释 + 函数 docstring

- **目标**：纯可读性提升。每段 `# ─── 区域名 ───` 起点写一两句职责说明，关键函数补 docstring。
- **零风险**，适合在拆分间隙做。

### M6. 给 services/ 各模块写一行职责注释

- **范围**：`ai_guardrails.py`、`ai_reports.py`、`crossref.py`、`dimension_scores.py`、`edit_history.py`、`file_store.py`、`llm.py`、`style_analysis.py` 顶部 docstring 统一格式。

---

## 🟢 P2 — 性能与体验

### X1. 文件树虚拟化或分页

- **场景**：项目文件非常多时（200+），`renderFileTree` 一次渲染 DOM 仍卡。
- **方案**：先做最简单的"超过 N 个文件时按目录折叠+按需展开"，不上虚拟列表库。
- **风险**：低（默认行为不变，只在文件多时收起）。

### X2. markIssuesInEditor 的 token 搜索优化

- **现状**：每个 issue 都会 `editor.getSearchCursor` 全文扫描 token。大文件 + 多 issue 时累加。
- **方案**：合并扫描——对每个文件只跑一次全文搜索，结果按 token 分发到对应 issue。

### X3. 编辑历史按文件分组视图

- **加分项**：当前时间线是全局倒序，可加一个"按文件聚合"视图，方便定位某文件的所有改动。
- **改动**：前端 only，沿用现有 API（`?file=` 参数已就绪）。

---

## 🔵 P3 — 商业化补完（需外部凭证或较大工作量）

### B1. 真实支付集成（**Blocker：需外部凭证**）

- 真 Alipay / Stripe 签名验签。需要你提供 app id / 私钥 / 公钥。

### B2. OAuth 登录（GitHub/Google）

- 需要 OAuth App credentials。

### B3. 定时清理为后台任务

- 7 天清理目前依赖启动钩子 + 手动调用，可上简单 APScheduler 或 cron 容器。

---

## 操作约定（自动化和我都遵守）

每完成一项**必走流水线**：

1. 改代码 → 自查 diff，只保留本轮相关
2. 跑验证：`ruff` + `pytest` + `npm run check:js` + `npm run test:js` + `npm run scan:secrets` + 禁用隧道策略扫描
3. 更新 [TODO.md](TODO.md) 勾选对应项
4. 更新 [CHANGELOG.md](CHANGELOG.md) 顶部新增版本，**版本号同步 `app/main.py`**
5. `git commit` 语义单一 → `git push origin main` → 验证远程已含 commit
6. 在本文件勾掉对应项，必要时新增后续项

**硬规则**：

- 永不使用 Cloudflare 或任何公网 tunnel
- AI 永不编造文献（reference authenticity 不调 LLM）
- 永不提交 secret / 论文内容 / `.env` / `data/secrets.enc` / `uploads/`
- 遇测试失败先修复，不绕过；改动可单独 revert
