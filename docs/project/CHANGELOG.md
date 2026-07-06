# ScholarLint · 投稿通 Changelog

## 2026-07-06 — fix: 全系统误报优化 + 路径规范化 + 图表评分修复
- **`gate_structure.py`**：图片路径反斜杠规范化（`\\` -> `/`）；子文件继承主文件 `\graphicspath`；新增常见子目录候选（figures/floats/imgs）
- **`gate_figures.py`**：dangling ref 错误信息改为中文；评分公式改为按 issue 扣分（5分/error + 2分/warning），真实论文 `figure_table_crossref` score 50→95
- **`gate_writing.py`**：各噪音阈值提高（双空格 10→30，超长句 5→10，被动语态 20→35，套话 5→8）；INFO 数量从 14→4
- **`tex_parser.py`**：图片路径在解析时规范化反斜杠
- **`gate_data.py`**：`\multicolumn` 展开、多行表头合并、新增 `from A to B` + `直接 metric-value` claim pattern；真实论文 claims 9→30，metric coverage 7→28；magnitude guard 消除跨量级 FP

## 2026-07-06 — feat: NCG scope 扩展 + 不可能值检测 + 模板残留检测
- **`gate_data.py`**
  - `_extract_claims`：`_METRICS` 扩展到 40+ 指标（BLEU-4/ROUGE-L/BERTScore/WER/pass@k 等）；`_DATASETS` 扩展到 30+ 数据集（GSM8K/HumanEval/WMT/CoNLL 等）；新增 `_MODEL_NAMES`（BERT/LLaMA/Mistral/Baseline 等方法名）
  - `_scope_sim`：新增 method 维度权重（+0.2）；metric 独立可达阈值（0.6），method/dataset 额外加分
  - `_check_impossible_values`（新）：表格列头含受限指标（accuracy/F1/precision/recall 等）且值 > 100 → ERROR；PPL < 1 → ERROR
  - `_extract_tables` 修复：`\\hline` 与数据行同块时正确拆分（之前会把数据行当 hline 跳过）
- **`gate_writing.py`**
  - 新增 `_TEMPLATE_REMNANTS` 词表（26 项：lorem ipsum/TODO:/[citation needed]/under review 等）
  - 扫描全文，发现模板残留 → ERROR，投稿前必须清除
- **`tests/test_gates.py`**：+4 新测试（impossible values ×2, template remnants ×2）；共 169 passed

## 2026-06-26 14:50 — Fix: cache 隔离 + OpenReview 搜索补充
- **`gate_references.py`**
  - `_DOI_CACHE` / `_TITLE_CACHE` 从模块级全局变量改为 `ReferenceAuthenticityGate` 实例变量（`self._doi_cache` / `self._title_cache`），消除多论文串行检查时的跨论文缓存污染（同 key 在第一篇因超时缓存为 `None` 后，后续论文不再重试）
  - `_search_by_title` 新增 OpenReview API（`https://api.openreview.net/notes/search`），在 Crossref/S2/OpenAlex 之后作为第三路搜索；覆盖 ICLR、COLM、NeurIPS Workshop 等不在 Crossref 数据库的论文

## 2026-06-26 — Fix: 误报大幅优化（data_integrity / writing_quality / reference_authenticity / inline bib）
- **`gate_data.py`**
  - 重复行检测：改为 per-group 报告（不再 pairwise 爆炸），且要求 ≥3 列才触发（2列的调查表格不报）
  - Benford 检测：跳过所有值在 [0,100] 区间的列（百分比/得分列），降误报
  - 评分公式：`total_findings * 15` → `error_count * 20 + warn_count * 5`，严格区分 severity
- **`gate_writing.py`**
  - AI marker 检测（"as an AI"/"I cannot"）：新增上下文过滤，引号内、verbatim 内、AI-response 引用语境中的匹配不触发 ERROR；解决 RealityTest 类论文的大量误报
- **`gate_references.py`**
  - 无 DOI 的 AI 模型卡片/技术报告（key 含 chatgpt/claude/gpt/gemini/llama 等，或 note 有 "technical report"/"blog" 字样）从 ERROR 降为 WARNING
- **`app/parsers/bbl_parser.py`**
  - 新增 `parse_inline_bibliography()` 和 `extract_inline_bib_entries()`：解析 `.tex` 文件中内联的 `\\begin{thebibliography}` 块
- **`app/core/check.py`** / **`app/api/routes.py`**
  - 加第三级 fallback：.bib → .bbl → inline thebibliography；解决单文件投稿无法解析引用的问题

## 2026-06-26 — Fix: .bbl 解析 + title 匹配误报修复
- **新增 `app/parsers/bbl_parser.py`**：解析 BibTeX 编译输出的 `.bbl` 文件（arxiv 投稿主流格式）
  - 支持 natbib 传统格式（`\bibitem[]{key}` + `\newblock`）和 biblatex refsection 格式（`\entry{}`）
  - 自动提取 key / title / authors / year / doi / url / venue
  - BERT (1810.04805) .bbl：56 条，54/56 有 year；GPT-3 (2005.14165) .bbl：144 条，全部有 year
- **`app/parsers/zip_parser.py`**：`identify_project_structure()` 新增收集 `.bbl` 文件，返回四元组 `(paper, tex_paths, bib_paths, bbl_paths)`
- **`app/core/check.py`**：当 `.bib` 为空时自动 fallback 到 `.bbl`，并在 metadata 写入 `bbl_used` 标志
- **`app/api/routes.py`**：同步应用 bbl fallback 逻辑（与 check.py 保持一致）
- **`app/checks/gate_references.py`**：
  - 新增 `_title_matches(a, b, threshold=0.85)`：先精确匹配，再 SequenceMatcher，再去空格 fallback（解决 "Socialiqa" ≠ "Social IQa" 的误报）
  - Step 4 标题验证、`_search_by_title` 三个 API 搜索处均改用 `_title_matches`
- 测试：pytest 7/7 绿（check_folder 全套）

## 2026-06-26 — Headless Check Pipeline (`app.core.check`)
- 新增 `app/core/check.py`：纯函数 `check_folder(folder, *, filename, job_id, gates) -> FullReport`，把"已解压目录 → 6 gate → FullReport"的核心检查链从 web 服务里独立出来；不依赖 FastAPI、不写盘、不动全局 dict、不修改文件夹
- 用途：CLI / 实验脚本 / 未来对外 API client 直接 `from app.core.check import check_folder` 三行调用，得到可序列化 `FullReport`（`.model_dump()` 转 JSON）
- 不动现有 web 路径：`app/api/routes.py` 的上传/解压/危险文件清理/进程级 dict / 持久化逻辑完全保留，向后兼容
- 新增 `app/core/__init__.py` 暴露 `check_folder` / `default_gates`
- 新增 `tests/test_check_folder.py`（7 项）：返回 FullReport / metadata 完整 / JSON 可序列化 / 自定义 filename+job_id / gate 子集 / 缺失目录抛错 / 不修改源文件夹
- 验证：ruff、pytest 162 项（原 155 + 新 7）全绿

## 2026-06-26 — Repo Root Cleanup
- 整理根目录：把营销/截图/Playwright 历史日志移入 `_Archive/`（policy: 永不删除，只 move），根目录现在只保留运行时代码、文档、配置
  - `_Archive/marketing/`：`IntegrityGuard_Demo.pptx` / `IntegrityGuard_Pitch_Deck.pptx` / `logo.png` / `create_ppt.py` / `create_ppt.js` / `take_screenshots.py`
  - `_Archive/screenshots/v50-historical/`（原 `screenshots/`，19 张 v48-v50 历史截图）
  - `_Archive/screenshots/v48-new/`（原 `screenshots_new/`，8 张早期 v48 截图）
  - `_Archive/dev-logs/playwright-mcp/`（原 `.playwright-mcp/`，500+ 个 console/page 历史快照）
- `.gitignore` 新增 `_Archive/`；`.gitignore` 中已经覆盖单文件名规则保持不变（向后兼容）
- 同步更新隧道扫描排除路径，移除 stale 的 `screenshots/` `screenshots_new/` `.playwright-mcp/`，统一改为 `_Archive/**`：`.github/workflows/ci.yml`、`scripts/secret-scan.mjs`、`docs/TESTING_GUIDE.md`、`HANDOVER.md`
- 验证：ruff、`npm run check:js`、`npm run scan:secrets`（114 文件 pass）、pytest 155 项全绿

## v5.4.1 (2026-06-02) — Tencent Cloud Lighthouse Deployment Bundle
- 新增 `docs/DEPLOY_TENCENT.md`：腾讯云 Lighthouse 一站式部署指南——实例选型（MVP/成长/扩展三档）、Ubuntu 22.04 + Docker 引导、目录布局（`/srv/scholarlint`，数据盘分离）、SSH 注入 `.env`（强调 secret 永不 git 化）、Nginx + 腾讯云 SSL 反代（含 `X-Forwarded-Proto` 触发 Secure cookie）、ICP 备案策略（mainland 必备 / 港新可绕过）、COS 加密备份、上线前自检清单、回滚步骤
- 新增 `docker-compose.prod.yml` overlay：localhost 绑定 + `env_file: .env` + 绝对数据卷路径（`/srv/scholarlint/data` 与 `/srv/scholarlint/uploads`）+ 有界 JSON-file 日志驱动（20MB×5）+ `restart: always`，与基础 compose 叠加使用
- 新增 `.env.example` 模板：所有生产环境变量（APP_ENV / PAYMENT_SANDBOX / LLM_* / JWT_SECRET / ADMIN_KEY / ALIPAY_* / 速率限制）含安全说明，明确指出 JWT_SECRET / ADMIN_KEY 留空让应用首次启动自动生成（持久化在 `data/.jwt_secret` / `data/.admin_key`）
- 新增 `scripts/check-no-secrets.mjs` + `npm run scan:tracked`：50ms 本地预推送自检，按文件名规则拒绝 `.env` / `data/secrets.enc` / `data/.jwt_secret` / `data/.admin_key` / `uploads/` / `*.pem` / `*private_key*` 进入 git index；`.env.example` 在白名单
- `.gitignore` 显式 `!.env.example` 例外，让模板能进库；docs/README.md 与根 README 索引同步加入新文档
- 安全边界硬性确认：现有 `.gitignore` 已经覆盖 `.env` / `.env.*` / `data/secrets.enc` / `data/.jwt_secret` / `data/.admin_key` / `uploads/`；本轮验证仓库当前没有任何 secret 入库
- 纯运维文档与配置补齐，无应用行为变化；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、新增 scan:tracked、隧道扫描、pytest 155 项

## v5.4.0 (2026-06-01) — Share-Token Report Redaction
- **安全修复**：`/api/report/{job_id}` 在 share-token 访问时会原样返回 `report.model_dump()`，导致 share-readonly 用户能拿到 `metadata.owner_id` / `owner_type` / `session_id` / `share_token` 与 `project_dir`，以及含学生私人理由的 `dismissed_issues` 列表
- 新增 `_share_readonly_report_payload()`：仅在 share-token 访问且非 owner 时启用——剥离 owner 标识、share token 自身、服务器内部 `project_dir`、整个 dismiss 审计列表；保留 gate 结果、得分、维度评分等导师审稿真正需要的字段
- 新增 `_is_owner()` helper 区分"通过 share-token 访问"vs"自己是 owner"，因为后者需保留完整 metadata 才能继续操作（编辑、撤销 dismiss 等）
- 不影响 markdown 导出 (`/api/export/{job_id}`)，导出本就走 share 模板（`SHARE_REPORT_TYPE`），这次修补的是 JSON API 路径
- 新增 `tests/test_share_report_redaction.py` 5 项：owner 看到完整字段 / share 看到脱敏字段 / 无 token 拒绝 / 错 token 拒绝 / redact helper 不修改输入（pytest 150→155）
- 通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.99 (2026-06-01) — File-Tree Render O(1) Per File
- 文件树渲染性能优化：`renderFileItem` 与 `getFileStatus` 原本为每个文件都遍历所有 gate × issue 调用 `issueMatchesFile`，复杂度 O(files × gates × issues)；改为 per-report 预建 `_fileIssueIndex`（basename → 错误/已驳回 计数）后变成 O(1) 查询
- 大型项目（多文件 × 多问题）文件树渲染明显更快；尤其与 v5.3.86（图片质检）+ v5.3.89（dismissed Map）形成完整的"O(n²)→O(n)"卡顿修复链
- 新索引严格沿用 `issueMatchesFile` 的归属规则（explicit `issue.file` / `bib:` 前缀适用所有 .bib / `issue.location` 中的文件名 token），并在 path 以 .bib 结尾时合并通用 `bib:` 桶
- 纯前端渲染优化，无 API/行为变化；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、pytest 150 项

## v5.3.98 (2026-06-01) — Extract permissions service
- 拆分上帝文件最后一刀（M4）：新增 `app/services/permissions.py`，把 `routes.py` 的**无状态**权限/会话 helper 集中到正式的 service 模块
- 迁出 9 个纯函数：`request_share_token`、`secure_session_cookie`、`set_session_cookie_if_needed`、`new_share_token`、`owner_metadata`、`extract_owner_metadata`、`request_uses_valid_share_token`、`owner_metadata_allows`、`can_access_report`；以及 `SESSION_COOKIE_NAME` / `SESSION_COOKIE_MAX_AGE` 两个常量
- 关键设计：`owner_metadata_allows` 与 `can_access_report` 通过 dependency injection 接收 `request_owner_loader` 参数，让新模块完全不依赖 routes.py 模块级状态（`_jobs` / `_job_owners` / etc.）；这样未来其它 router 可以直接 import permissions 而不用借 routes 跳板
- routes.py 改为薄 wrapper（`_owner_metadata_allows` / `_can_access_report` 绑定到本地 `_get_request_owner`），原 9 个 helper 名通过 `from … import … as _xxx` re-export 保持向后兼容；`_get_request_owner` 留在 routes.py（它必须 import `app.dependencies`，否则会形成 permissions ↔ dependencies 循环依赖）
- 新增 `tests/test_permissions_service.py` 17 项：share-token 解析（header / 缺失 / strip 空白）、Secure flag 决策矩阵（prod / 别名 / local / x-forwarded-proto）、owner_metadata 自动生成 / 显式 token / 保留 session_id、extract 容错、决策树（legacy local 放行 / production 拒绝 / owner 写权限 / share 只读 / allow_share=False / 错误 token）
- 通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描、pytest 133→150（新增 17 个 permissions 单元测试）

## v5.3.97 (2026-06-01) — routes.py Module-Level Documentation
- 给 `app/api/routes.py` 写完整的模块级 docstring：列出剩余端点（upload/status/report/edit-history/recheck/dismiss/export/history/compare/score-trend/analysis/job-delete/AI batch）、共享基础设施（进程级状态、权限/会话/速率限制/LLM 网关 helper），并明确兄弟 router（file_routes/tool_routes/checklist_routes/ai_routes）依赖此处提供的单一权威来源
- 显式记录三条安全/操作不变量：legacy job 在 prod 拒绝（S1）、reference-authenticity 不调 LLM、日志走 `redact()` 脱敏
- 关键 helper 加详细 docstring：`_get_request_owner` 三步解析顺序、`_owner_metadata_allows` 决策树、`_require_job_access` 的 403/404/None 三种返回路径、`_get_report` 缓存 rehydrate 行为、`_owner_metadata` / `_extract_owner_metadata` / `_request_uses_valid_share_token`（明确 `compare_digest` 防时序侧信道）
- 关键端点加 docstring：`/upload`（4 步流水线含计费扣减与背景任务）、`/status`（轮询语义）、`/report`（202 still-processing 行为，dimension_scores 即时计算）
- 模块级状态变量加 inline 注释说明用途与由 `clear_route_state` 清理；`__all__` 加注释说明跨模块调用的隐式公共界面
- 纯文档/可读性改动，零行为变化；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描、pytest 133 项

## v5.3.96 (2026-06-01) — Split checklist_routes from routes.py
- 拆分上帝文件第三刀：新增 `app/api/checklist_routes.py`，迁出 `POST /api/venue-checklist/{job_id}` 端点（ARR/NeurIPS 复现性 checklist AI 自动填充）
- 新模块顶部统一 `import httpx` / `import json`（替换原有的内嵌惰性导入），LLM 系统提示和不变量保持不变（缺证据答 no、不臆造结论）
- `routes.py` 删除该端点定义，并移除 `from app.checklists import CHECKLISTS` 这条已无用 import
- `main.py` 挂载新 router；外部 URL 不变；纯结构性重构，pytest 133 项全过；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.95 (2026-06-01) — Split tool_routes from routes.py
- 拆分上帝文件第二刀：新增 `app/api/tool_routes.py`，迁出 5 个工具端点：`POST /api/bib-clean/{job_id}`、`GET /api/fetch-bib/{doi}`、`POST /api/reference-candidates/{job_id}`、`GET|POST /api/tidyup/{job_id}`、`POST /api/format-normalize/{job_id}`
- 新模块顶部固定 `import httpx`（之前 5 处惰性导入冗余），统一 `from app.api.routes import _require_job_access, _get_report, _job_dirs` 复用权限/状态
- 引用候选逻辑保留对 `app.services.ai_guardrails` 的直接 import（`candidate_from_crossref` / `s2` / `openalex` / `extract_reference_title`），不再借助 `routes.py` 的 re-export 跳板
- `routes.py` 删除 5 个端点定义、清理 `__all__` 中已不再 re-export 的 4 个名字、移除对应 ai_guardrails import；`tests/test_ai_integrity.py` 改为直接从 `ai_guardrails` 导入
- 外部 URL 完全不变；`main.py` 挂载新 router；纯结构性重构，pytest 133 项全过；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.94 (2026-06-01) — Split file_routes from routes.py
- 拆分上帝文件第一刀：新增 `app/api/file_routes.py`，从 `app/api/routes.py` 迁出 4 个端点：`GET /api/files/{job_id}`（列表）、`GET /api/files/{job_id}/{file_path}`（读）、`PUT /api/files/{job_id}/{file_path}`（写）、`GET /api/download/{job_id}`（项目 ZIP）
- 外部 URL 完全不变；新模块通过 import `routes` 私有 helper（`_require_job_access` / `_get_report` / `_job_dirs`）保持权限校验、状态管理、edit_history 追踪等行为完全一致
- `main.py` 挂载新 router，原 routes.py 删除对应 4 段端点定义并清理未用 import（`StreamingResponse` / `list_editable_files` / `project_zip_bytes`）
- 4 个相关测试 fixture（test_e2e_minimal、test_edit_history、test_job_ownership、test_upload_api）同步挂载新 router
- 纯结构性重构，零行为变化；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、pytest 133 项

## v5.3.93 (2026-06-01) — Anonymous Session Cookie Secure Alignment
- 匿名 `sl_session` cookie 的 Secure 标志原本写死 `False`，与登录 cookie 的"生产/HTTPS 自动 Secure"行为不一致
- 新增 `_secure_session_cookie(request)` 判断（与 `auth_routes._secure_cookie` 同款逻辑）：`app_env=prod/production`、`request.url.scheme=https`、或 `x-forwarded-proto=https` 任一成立即设 Secure
- 本地默认仍不带 Secure，避免开发场景被浏览器丢弃；公网部署/反向代理 HTTPS 时自动启用，Cookie 不会再以明文穿越 HTTP
- 新增 `tests/test_session_cookie_secure.py` 6 项：local 不 Secure、production/prod 强制 Secure、`x-forwarded-proto=https` 触发、helper 决策矩阵（pytest 127→133）
- 通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.92 (2026-06-01) — API Token Authentication
- Pro/Team API Token 真正接入业务接口鉴权：`get_current_user_optional` 在 `Authorization: Bearer sl_api_…` 时按 SHA-256 hash 查 `api_tokens` 表，命中且未撤销则返回对应用户；其他 Bearer 值仍按 JWT 解码（向后兼容）
- 命中后写 `last_used_at` 时间戳，便于审计；未知/已撤销 token 静默返回 None（不泄露存在性）
- 新增 `tests/test_api_token_auth.py` 7 项：有效 token / 未知 token / 已撤销 / last_used_at 写入 / 无凭证 / 合法 JWT Bearer 仍工作 / 非法 JWT 拒绝（pytest 120→127）
- 修复 SQLAlchemy detached-instance 陷阱：commit 后重新查询 user 并 expunge，使 dependency 返回的对象在 session 关闭后仍可读属性
- 通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.91 (2026-06-01) — Legacy Job Tightened in Production
- 修复生产权限旁路：`_owner_metadata_allows()` 原本对缺少 `owner_type/owner_id` 的旧 job 一律放行（本地 demo 兼容），上线公网后等同于"猜中 job_id 即可访问"
- 当 `settings.app_env in {"prod", "production"}` 时，缺 owner metadata 的 job 一律返回 403；本地默认 `app_env=local` 行为保持不变（旧报告仍可访问）
- 新增 `tests/test_legacy_owner_strict.py` 4 项：本地放行、`production`/`prod` 别名拒绝、有 owner 的 job 在生产仍正常访问（pytest 116→120）
- 通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.90 (2026-06-01) — Hardened Secret Redaction
- 新增工作计划清单 `WORK_PLAN.md`：按 P0 安全/P1 可维护性/P2 性能/P3 商业化分组列出可一轮完成的执行项，配合 TODO.md 与 HANDOVER.md 使用
- 扩展 `secrets_manager.redact()`：除原有 LLM key/url 字面替换外，覆盖 JWT (`eyJ…`)、`Authorization: Bearer …`、内部 LLM key 前缀、API token 前缀 `sl_…`、PEM 私钥/证书块；同时把 `JWT_SECRET`、`ADMIN_KEY`、`ALIPAY_*` 加入已知敏感名单按值替换
- 新增 `tests/test_redact.py` 8 项：覆盖每种模式被替换、正常文本不误伤、空输入安全（pytest 108→116）
- secret-scan 排除 `app/secrets_manager.py` 与 `tests/test_redact.py`（合法定义/测试 redaction 规则的位置）；CI 隧道扫描排除 `WORK_PLAN.md`（与 CHANGELOG 同等地位，需提及禁用词作为执行准则）
- 防御性提升，无 API/行为变化；通过 ruff、JS 检查、JS helper 测试 7 项、secret scan、隧道扫描

## v5.3.89 (2026-05-31) — Dismissed-Issue Lookup Perf
- 前端新增共享 `isDismissed(gateName, idx)` helper：按 report 缓存一个 `gate::index` 的 Set，复用查询，report 变化时自动重建
- 文件树徽章（`renderFileItem`）、文件状态（`getFileStatus`）、编辑器标记（`markIssuesInEditor`）、问题收集与复制清单等 6 处原本对每个 issue 都扫描整个 `dismissed_issues` 数组（O(文件×gate×issue×dismissed)），改为 O(1) 查询，文件/问题多时文件树渲染更顺畅
- 纯前端性能与可维护性优化，统一 dismissed 判定入口；保留 `renderIssues` 内需要取 dismiss 理由的本地 Map（用途不同）
- 通过 JS 语法检查、JS helper 测试 7 项、pytest 108 项

## v5.3.88 (2026-05-31) — Edit History & Revert
- 新增编辑修改历史功能：用户每次保存文件都会记录一条历史（时间、文件、行数增减、改动前后内容）
- 新增 `app/services/edit_history.py`：历史加密存储于 `data/jobs/{job_id}.history.enc`（与报告同等保护，含论文内容必须加密），最多保留 100 条，超大快照（>512KB）仅存摘要不可回退，避免历史无限膨胀；内容未变化的保存不记录
- 新增三个接口：`GET /api/history-edits/{job_id}`（时间线列表）、`GET /api/history-edits/{job_id}/{entry_id}`（改动前后内容用于 diff）、`POST /api/history-edits/{job_id}/{entry_id}/revert`（回退到改动前，回退本身也记入历史，可再次撤销）
- 权限：查看历史需 read 权限（owner 或 share token），回退需 write 权限（share token 只读用户被拒 403）；删除 job 时一并清理历史
- 工作台工具栏新增「📜 修改历史」入口：时间线弹窗展示每次改动（文件名、时间、+/- 行数徽章），可查看行级 diff（红删绿增）并一键回退；回退后自动刷新编辑器
- 历史记录为 best-effort，记录失败绝不影响用户保存；新增 `tests/test_edit_history.py` 覆盖记录、无变化跳过、diff、回退恢复、share token 拒绝回退（pytest 103 → 108）
- 通过 ruff、JS 语法检查、JS helper 测试 7 项、secret scan

## v5.3.87 (2026-05-31) — Shared Test Fixtures
- 新增 `tests/conftest.py`，集中提供 `clear_route_state()` 与 `reset_route_state` fixture，统一清理 `app.api.routes` 的 9 个进程级状态（jobs/status/dirs/progress/owners/locks/rate_limit/llm_calls），保证测试间隔离
- `test_ai_routes.py`、`test_e2e_minimal.py`、`test_export_report.py`、`test_job_ownership.py`、`test_upload_api.py` 改用共享清理函数，移除各自重复的 setup/teardown 清理代码
- 各文件统一为清理全部 9 个状态（原先有的只清 6-7 个子集）；测试内部刻意只清部分状态以模拟重启恢复的逻辑保持原样不动
- 纯测试基础设施重构，降低维护成本、便于交接；app 运行时行为零变化，pytest 仍 103 项全过，ruff/secret scan 通过

## v5.3.86 (2026-05-31) — Image-Heavy Project Performance
- 修复含大量图表的项目质检卡顿：StructureGate 重复图检测与图片质量检测原本各自全目录遍历一次（两次 rglob），且对每张图 `read_bytes()` 整图入内存算 MD5
- 合并为单次目录遍历，复用同一份图片清单做重复检测与质量提示
- 重复图检测改为先按文件大小分组，仅对大小相同的候选才计算 MD5（绝大多数图大小唯一，直接跳过昂贵 hash），语义仍为“内容完全相同”
- MD5 改为分块流式计算，`_raster_dimensions` 改为只读 PNG 头 24 字节 / JPEG 到 SOF marker，不再整图读入内存；实测单张 12MB 图峰值内存 12MB → 2.1MB，MD5 与尺寸结果一致
- 前端 issue 列表渲染预建 dismissed_issues 的 Map，按 `gate::index` O(1) 查询，替换原先每条 issue 对整个 dismissed 数组的 some/find 扫描（大量问题时减少 O(m×n)）
- 新增重复图检测测试（相同内容报重复、不同大小不报），pytest 101 → 103；通过 ruff、JS 语法检查、JS helper 测试 7 项

## v5.3.85 (2026-05-31) — Diagnosis Report Layout Polish
- 修复 AI 论文诊断报告弹窗排版错位：优先级列表改用 flex 布局，编号徽章与多行文本左缘严格对齐，标题/原因/行动/位置不再随换行飘移
- 重排弹窗结构：「先改哪三处」升为整行展示（信息密度最高），不再与「预计时间」并排导致左右卡片高度悬殊；其余分区改为协调的 2×2 等宽网格
- 统一各分区表头样式（图标 + 标题）和核心摘要标签，列表项使用一致的项目符号与行高，整体对齐基线一致
- 纯前端模板改动，无后端/接口变化；通过 JS 语法检查、JS helper 测试 7 项与 pytest 101 项

## v5.3.84 (2026-05-31) — Engineering Docs Baseline
- 新增 `docs/ARCHITECTURE.md`：系统分层、应用入口、上传→报告请求流、六类 gate、parser/service 职责、AI guardrail 不可破坏不变量、权限模型（owner/share-token/legacy 兼容）、存储加密、健康探针和已知可维护性风险
- 新增 `docs/CONFIGURATION.md`：逐项列出 `config.py` 的密钥、LLM 用量上限、服务器、路径、Crossref、gate 阈值、计费与支付设置，含默认值、来源优先级（env → 加密库）和生产建议
- 新增 `docs/API_OVERVIEW.md`：按 router（core/ai/auth/payment）分组列出全部端点、方法、访问权限与用途，路径经核对 router prefix（`/api/auth`、`/api/payment`）准确无误
- 文档内容逐一对照真实代码核实：端点取自路由装饰器、配置取自 `config.py` 字段、权限取自 `_require_job_access` 与 `dependencies.py`，确保可交接给工程师直接使用
- `docs/README.md` 索引补入架构/配置/API 三篇并链接 root README 与 HANDOVER；纯文档交付，无运行时行为变化

## v5.3.83 (2026-05-31) — Root README
- 新增根目录 `README.md`，提供项目定位、能力概览、目录结构、请求流程、快速启动、健康检查、测试验证、文档索引和操作红线
- README 对齐当前实际代码：六类 gate、AI 路由拆分现状、`/healthz` `/readyz` `/metrics` 探针和统一验证命令集，改善 GitHub onboarding
- `.gitignore` 忽略 `.workbuddy/`（agent 工作区数据），并在 secret scan 与禁用隧道策略扫描中同步排除，避免本地工作区笔记触发误报
- 纯文档与工程卫生改动，不引入新依赖或运行时行为变化

## v5.3.82 (2026-05-31) — AI Handover Document
- 新增根目录 `HANDOVER.md`，为后续 AI/agent 接手提供当前版本、项目目标、操作规则、架构概览和安全注意事项
- 记录近期商业化与工程基线提交、验证命令、重点风险、推荐下一步和禁止事项
- `TODO.md` 同步记录 AI 交接文档已完成，方便后续从任务清单定位

## v5.3.81 (2026-05-31) — Paid Tier API Token Foundation
- 新增 `api_tokens` 数据表，支持 Pro/Team 用户创建、查看和撤销个人 API Token
- API Token 明文只在创建时返回一次，服务端仅保存 SHA-256 hash 和短前缀，降低泄露风险
- Free 用户访问 API Token 列表、创建和撤销接口会返回 403，付费 tier 权益边界更清晰
- 新增测试覆盖付费 tier 限制、token 只返回一次、hash 存储和撤销后列表隐藏
- `TODO.md` 记录 Pro/Team API Token 基础能力已完成，为后续 CLI/API 接入铺路

## v5.3.80 (2026-05-31) — Hardened CI Safety Checks
- GitHub Actions 安装流程补齐 `python -m pip` 与 `npm ci`，确保 JS helper 测试和 secret scan 在干净环境可复现
- CI ruff 命令与本地验证对齐，纳入 `scripts/backup_data.py`
- 禁用隧道 provider policy scan 改为运行时拼接 pattern，不再排除 workflow 文件自身，避免 CI 配置成为扫描盲区
- 前端 JS 语法检查改为调用 `npm run check:js`，和本地命令保持一致
- `TODO.md` 新增并完成 CI 安全测试闭环子项，deploy 仍保留为后续独立事项

## v5.3.79 (2026-05-31) — Team Mentor Dashboard
- `/auth/dashboard` 对 Team tier 用户新增 `team_dashboard`，基于最近 50 次检查计算平均分、通过率、待关注数量和低分论文列表
- 账户弹窗新增导师 Dashboard 品牌卡片，展示 Team 视角核心指标并支持直接打开待关注论文
- 不引入外部账号或团队成员表，先用当前 Team 用户自己的历史检查跑通导师视角 MVP
- 新增测试覆盖 Team dashboard 汇总计算、低分列表排序和响应结构，`TODO.md` 记录该权益切片已完成

## v5.3.78 (2026-05-31) — Paid Package Tier Upgrade
- 专业包现在声明 `tier=pro`，实验室包声明 `tier=team`，套餐列表会返回对应权益信息
- 支付入账时自动应用套餐 tier：购买专业包升级 Pro，购买实验室包升级 Team，且不会从 Team 降级回 Pro
- 支付回调幂等路径也会补齐 tier 升级，历史已入账订单重复回调不会重复加 credits
- Sandbox 充值响应返回 `new_tier`，前端即时刷新当前用户 tier，使 Pro/Team 无限检查权益立即生效
- 新增测试覆盖 Pro/Lab 套餐升级、回调幂等和防降级，`TODO.md` 记录付费套餐自动升级已完成

## v5.3.77 (2026-05-31) — Pro Tier Unlimited Check Entitlement
- 新增 `UNLIMITED_CHECK_TIERS` 与 `deduct_check_credit()`，Pro/Team 用户完整质检不再消耗免费检查次数
- 上传扣费路径改用权益感知扣费，Free 用户仍按配置消耗 1 次并保留余额不足保护
- 前端上传前余额判断识别 Pro/Team tier，避免 0 次余额的付费用户被错误拦截
- 更新测试覆盖 Pro/Team unlimited entitlement 不生成 consume 交易，`TODO.md` 记录该权益切片已完成

## v5.3.76 (2026-05-31) — Free Tier Monthly Refresh
- 新增 Free tier 月度懒刷新：老用户每月余额低于 3 次时自动补足到 3 次
- 登录、OAuth 复用、`/auth/me`、dashboard 和上传扣费前都会触发刷新，避免需要额外后台任务
- 月度赠送写入 `Transaction` gift 记录，按月份去重，避免同月重复领取
- 更新用户模型默认额度注释和测试，覆盖月度补足与同月幂等

## v5.3.75 (2026-05-31) — Free Tier Credit Alignment
- 注册和 OAuth 新用户默认赠送 3 次免费质检，统一为 `FREE_TIER_STARTING_CREDITS`
- 修复前端上传前余额判断：完整质检实际消耗 1 次，不再错误要求 10 次余额
- 更新注册成功提示为“赠送 3 次免费质检”，新增测试覆盖注册赠送额度
- `TODO.md` 同步记录 Free tier 注册赠送 3 次已完成，并拆出月度重置为后续独立项

## v5.3.74 (2026-05-31) — Multi-Dimensional Scores
- 新增 `app/services/dimension_scores.py`，从现有 gate 分数派生 Novelty / Soundness / Clarity / Significance 四维启发式评分
- `/api/report/{job_id}` 返回 `dimension_scores`，概览页新增多维度评分卡片和四个维度分数条
- 新增 `tests/test_dimension_scores.py` 覆盖维度计算、分数边界和缺 gate 时的 fallback 行为
- `TODO.md` 同步记录四维评分已完成；基于 OpenReview 的 venue 均分对比仍保留为后续项

## v5.3.73 (2026-05-31) — TODO Auth Alignment
- `TODO.md` 对齐当前实现状态：邮箱 + 密码注册/登录已存在并有前端入口、JWT/cookie 会话和安全测试覆盖
- 将 GitHub/Google OAuth 从混合描述拆成后续独立 TODO，避免把已完成邮箱登录和未做 OAuth 混在同一项里

## v5.3.72 (2026-05-31) — Writing Style Analysis
- 新增 `app/services/style_analysis.py`，从 LaTeX 文本中剥离命令/引用/注释后计算词汇多样性、平均句长、长句比例和高频重复词
- `/api/analysis/{job_id}` 返回 `writing_style` 指标，前端分析弹窗新增“写作风格分析”卡片和可读性提示
- 新增 `tests/test_style_analysis.py` 覆盖复杂句、重复词、注释/引用剥离和空文本行为
- `TODO.md` 同步记录写作风格分析已完成

## v5.3.71 (2026-05-31) — Image Quality Hints
- Structure gate 增加图片质量与优化提示：检测短边低于 600px 的 PNG/JPEG 栅格图，提示替换高分辨率图或矢量图
- 检测超过 5MB 的图片/PDF 资产，提示压缩或避免嵌入未压缩截图
- 新增结构 gate 测试覆盖低像素 PNG 和过大 PDF 图片告警
- `TODO.md` 同步记录图片优化建议已完成，并注明图表字体可读性仍待独立实现

## v5.3.70 (2026-05-31) — Citation Command Normalization
- LaTeX format normalizer 增加 `citation_cmd` 规则，保守地将裸 `\cite{...}` / `\cite[...]{...}` 统一为 `\citep...`
- 规则会跳过注释行，并保留 `\citet`、`\citep` 等已有语义不同或已规范的引用命令
- 新增测试覆盖裸 cite、带 optional args 的 cite、注释行和 `\citet` 保留行为
- `TODO.md` 同步记录一键格式规范化的引用格式子项已完成

## v5.3.69 (2026-05-31) — User Dashboard Checks
- `/api/auth/dashboard` 增加当前用户最近论文检查记录，按 user owner 过滤，不混入匿名或其他用户 job
- “我的账户”弹窗升级为 dashboard：展示剩余次数、累计质检、会员等级、最近论文列表和积分记录，并可直接跳转恢复历史报告
- 新增 dashboard API 测试，覆盖最近检查 owner 过滤参数与统计返回
- `TODO.md` 同步记录用户 dashboard 已完成

## v5.3.68 (2026-05-31) — Blank Line Normalization
- LaTeX format normalizer 增加 `blank_lines` 规则，将 3 个及以上连续空行压缩为 2 个，保留段落分隔同时清理噪声空白
- 扩展格式规范化测试，覆盖多余空行压缩以及变更记录
- `TODO.md` 同步记录基础排版空白清理已覆盖多余空行

## v5.3.67 (2026-05-31) — Format Normalize Entry
- 工作台 toolbar 增加“规范格式”入口，让已有 LaTeX format normalization 不再只藏在右键菜单里
- 格式规范化请求改用统一 `apiFetch`，继承现有错误处理、权限与会话语义
- 新增 `tests/test_format_normalizer.py` 覆盖 Table/Figure 非断行空格、Fig./Eq. ref 空格、行尾空白和注释空格规则
- `TODO.md` 同步记录一键格式规范化入口、数字格式、缩写与基础空白清理已完成

## v5.3.66 (2026-05-31) — Report Comparison View
- 概览页新增前后两次检查对比卡片，复用 `/api/compare/{job_id}` 展示总分、错误数、警告数变化
- 对比卡片增加 gate 级状态与分数变化，支持跳转查看上一次检查记录
- `TODO.md` 同步记录对比视图已完成

## v5.3.65 (2026-05-31) — Data Backup Strategy
- 新增 `scripts/backup_data.py`，默认备份 `data/` 到带 manifest 的 ZIP，可选 `--include-uploads` 纳入用户上传文件，并支持 `--dry-run` 预览
- SQLite 文件通过 SQLite backup API 写入归档，降低运行中直接复制数据库导致不一致的风险
- 新增 `docs/BACKUP.md`，说明备份范围、uploads 边界、加密存储提醒和 restore smoke checks；文档索引、部署文档与 release checklist 同步引用
- `TODO.md` 同步记录数据备份策略已完成，并忽略本地 `backups/` 归档目录

## v5.3.64 (2026-05-31) — Lightweight Monitoring
- 新增进程内请求监控，记录服务启动时间、uptime、总请求数、5xx 错误数、错误率、平均/最大延迟和最近窗口统计
- 新增 `/metrics` JSON endpoint，按接口聚合请求量、错误量、延迟与最近状态码，并对高基数字段做路径脱敏，避免泄露 job id、share token 或长文件名
- `docs/DEPLOY_SAFE.md` 增加 `/metrics` 运维说明，`TODO.md` 同步记录监控项已完成
- 新增测试覆盖 `/metrics` 输出和路径脱敏行为

## v5.3.63 (2026-05-31) — Frontend Loading Skeleton
- 前端补齐复用型 loading skeleton：恢复历史报告时会先渲染概览页占位，包括 gate 节点、统计区、检查卡片和提交建议区域
- 首页最近检查历史加载时显示轻量骨架屏，并在无历史记录时主动收起历史区，避免残留旧状态
- `TODO.md` 同步记录 Loading skeleton 已完成

## v5.3.62 (2026-05-30) — Safe Deployment Docs
- 新增 `docs/DEPLOY_SAFE.md`，覆盖 Docker + 反向代理 + HTTPS 的生产部署形态、`APP_ENV=production`、支付 sandbox 下线前检查、密钥注入、上传 ZIP 安全、日志、健康检查、备份与公网暴露复核
- `docs/README.md` 增加 Safe Production Deployment 入口，`docs/RELEASE_CHECKLIST.md` 增加发布前阅读部署指南并确认生产开关的步骤
- `TODO.md` 同步记录安全部署文档已补齐
- 本地验证通过：no tunnel provider policy scan、`npm run scan:secrets`、`npm run check:js`、`npm run test:js`、`python -m pytest -q`

## v5.3.61 (2026-05-30) — Do Not Do Docs
- 新增 `docs/DO_NOT_DO.md`，集中列出研究真实性、AI 修复验证、仓库卫生、敏感文件/密钥与公网暴露禁止事项
- `docs/README.md` 增加 Do Not Do 入口，`docs/RELEASE_CHECKLIST.md` 增加发布前 guardrail 复核步骤
- `TODO.md` 同步记录禁止事项文档已补齐

## v5.3.60 (2026-05-30) — Testing Guide Docs
- 新增 `docs/TESTING_GUIDE.md`，按全量提交前、前端 JS、AI routes/integrity、upload/file security、parser/gates、auth/payment、export/brand、minimal E2E、dependency audit/coverage 分类整理当前测试命令
- `docs/README.md` 增加 Testing Guide 入口，`docs/RELEASE_CHECKLIST.md` 改为引用统一测试指南，减少发布检查命令重复
- `TODO.md` 同步记录本地运行、测试与发布文档已补齐

## v5.3.59 (2026-05-30) — Local Docs And Release Checks
- 新增 `docs/README.md` 作为文档索引，链接本地运行指南与发布清单，并预留测试、禁止事项和安全部署文档入口
- 新增 `docs/LOCAL_RUN.md`，覆盖本地依赖安装、密钥初始化、uvicorn/Docker Compose 启动、健康检查、数据目录与 localhost 演示边界
- 扩展 `docs/RELEASE_CHECKLIST.md`，补充 JS helper 测试、ruff、pip-audit、文档索引确认和 `app/main.py` 版本与 changelog 顶部对齐提醒，并将应用版本对齐到 `5.3.59`

## v5.3.58 (2026-05-30) — Frontend Draft Save Retry
- 编辑器按文件维护 dirty / saving / error / pendingContent 状态，tab 会显示未保存或保存失败指示
- 编辑变更会按 job ID 与文件路径写入 localStorage 草稿，auto-save 成功后清除草稿，失败后保留未同步内容并显示明确 toast
- 打开文件时若发现本地草稿与服务端内容不同，会优先恢复草稿并提示用户，可通过顶部“重试保存”重新同步当前文件

## v5.3.57 (2026-05-30) — Branded Markdown Export Header
- 后端 Markdown 导出报告新增统一品牌 header/footer，包含报告 ID、检查时间、导出时间、报告类型、官网与免责声明
- 分享链接导出会标记为「导师只读分享版」，作者工作区导出标记为「作者工作区版」，保留原有 gate 详情正文
- 新增导出 API 回归测试覆盖作者与分享两条路径，确认报告不再出现旧品牌名

## v5.3.56 (2026-05-30) — Frontend Brand Unification
- 导出 Markdown 报告标题、证书页脚与独立报告页标题统一使用 `ScholarLint · 投稿通` 对外品牌
- Crossref、Semantic Scholar/OpenAlex 相关对外 HTTP User-Agent 去除旧 `IntegrityAssurance/0.1` 标识，改用 `ScholarLint/5.3` 风格

## v5.3.55 (2026-05-30) — Brand Logo Static Asset
- 新增正式静态品牌资产 `app/static/brand/logo.png`，用于页面内稳定引用，根目录临时 `logo.png` 保持未纳入提交
- 全局 navbar 改用 34px 品牌 logo，并保留原渐变盾牌作为图片加载失败 fallback，点击回首页行为不变
- 上传页 hero 左侧品牌图标改用同一 logo 路径，保持原有布局与文案不变

## v5.3.54 (2026-05-30) — Minimal API E2E Recheck Coverage
- 新增 `tests/test_e2e_minimal.py`，用 FastAPI TestClient 挂载真实 API router，覆盖上传 ZIP、查看报告、列文件、读取/保存 `main.tex`、重新质检与报告刷新
- E2E 不 mock `_run_checks`，仅 stub `ReferenceAuthenticityGate.check` 避免外网，确保真实解压、文件保存和 gate 编排参与流程
- 通过 figure 缺少 `\label` 的稳定用例验证编辑后 recheck 会清除 `figure_table_crossref` 问题并提升 gate 分数

## v5.3.53 (2026-05-30) — Parser Graphicspath Test Coverage
- 新增 parser 回归测试，确认无扩展名 `\includegraphics{plot}` 与带 optional args 的路径会原样进入 `TexFile.graphics`，注释内图片命令会被忽略
- 扩展 StructureGate 测试，覆盖 `\graphicspath` 下无扩展名图片匹配 `.png/.pdf/.jpg/.jpeg/.eps`、多目录解析和无支持后缀时的缺图 warning

## v5.3.52 (2026-05-29) — Upload API Integration Tests
- 新增 `tests/test_upload_api.py`，用 FastAPI TestClient 挂载真实 upload router，并隔离上传目录与 job 存储到临时目录
- 上传测试不 mock `_run_checks`，仅 stub `ReferenceAuthenticityGate.check`，避免访问 Crossref/Semantic Scholar/OpenAlex，同时覆盖真实解压、结构 gate 与报告持久化
- 覆盖有效 ZIP、非 `.zip` 后缀、损坏 ZIP、Zip Slip、危险文件清理、缺 `.tex` 与缺 `.bib` 等 API 行为

## v5.3.51 (2026-05-29) — Frontend Helper Tests
- 新增 `app/static/js/helpers.js`，把 inline script 中可复用的纯前端 helper 抽为非 module 全局脚本，保留现有 onclick/inline 调用方式
- 批量 AI 修复前端改用 `groupFixesByGate()`、`indexesForGate()`、`prepareFixText()` 与 `$` 安全的 `replaceOnce()`，减少模板内重复逻辑
- 新增 `scripts/test-js-helpers.mjs`，用 Node 内置 test 覆盖 helper 行为，并在 CI 前端语法检查后运行 `npm run test:js`

## v5.3.50 (2026-05-29) — CI Secret Scan Coverage
- 新增 `scripts/secret-scan.mjs`，CI secret scan 改为复用本地无依赖脚本；脚本仅排除自身和本地生成目录，workflow 与 tracked data/config 仍会被扫描
- Secret scan 扩展覆盖内部 LLM endpoint/key、Bearer key、Cloudflare token/key、JWT/admin credential、payment provider key 与 private key block
- Release checklist 改为可执行的 `npm run scan:secrets` 本地检查命令，TODO 同步记录 CI secret scan 覆盖范围
- 本地验证通过：`npm run scan:secrets`、`npm run check:js`、`python -m pytest -q`

## v5.3.49 (2026-05-29) — CI Syntax Check Script
- 新增 `scripts/check-inline-js.mjs`，把 GitHub Actions 里 inline `<script>` 语法解析抽成本地可复用 Node 脚本
- CI 前端语法检查改为执行脚本，并新增 no-Cloudflare policy scan，排除 workflow 自身与本地数据/上传/截图目录避免自检误报
- Release checklist、TODO 补充本地 `npm run check:js` 与 policy scan 自检步骤
- 本地验证通过：`npm run check:js`、no-Cloudflare policy scan、`python -m pytest -q`（65 项）

## v5.3.48 (2026-05-29) — AI Router Share-Token Permission Test
- `tests/test_ai_routes.py` 的 AI fixture 现在带 session owner 与 share token metadata，成功路径不再依赖 legacy 无 owner 默认放行
- 新增 share-token 只读权限测试，确认 `POST /api/ai-diagnosis/{job_id}?share=...` 返回 403
- 测试通过 monkeypatch 阻断 `_llm_chat_post`，确保权限拒绝发生在真实 LLM 调用之前
- 本地验证通过：AI router tests 7 项；全量 pytest 65 项

## v5.3.47 (2026-05-29) — AI Diagnosis API Tests
- 扩展 `tests/test_ai_routes.py`，为 `POST /api/ai-diagnosis/{job_id}` 增加 API-level mock 测试
- 覆盖模型返回普通 JSON 与 fenced JSON 的成功解析路径，并断言 provenance 包含 source、model、gates
- 覆盖 LLM 非 200 fallback 与 missing job 404，确保失败路径不真实调用 LLM
- 成功路径 mock 会验证 prompt 包含 gate、issue、文件与行号，同时不泄露 `project_dir` 或临时路径
- 本地验证通过：AI router tests 6 项；全量 pytest 64 项

## v5.3.46 (2026-05-29) — AI Router Guardrail API Tests
- 新增 `tests/test_ai_routes.py`，用 FastAPI TestClient 直接覆盖新 `ai_routes.py`
- 验证 `POST /api/ai-fix/{job_id}` 遇到 reference authenticity 问题时返回 `not_fixable`，且不会调用 LLM
- 验证 `POST /api/ai-batch-fix/{job_id}` 对 reference authenticity 问题只返回 dry-run skipped summary，不生成 AI 修复
- 本地验证通过：AI focused tests 12 项；全量 pytest 60 项

## v5.3.45 (2026-05-29) — AI Fix 路由完成迁移
- `POST /api/ai-fix/{job_id}` 与 `POST /api/ai-batch-fix/{job_id}` 已迁入 `app/api/ai_routes.py`
- 当前所有 `/api/ai-*` 路径集中到 AI router，旧 `routes.py` 仅保留 batch candidate helper 等迁移期共享逻辑
- 保留 reference-authenticity guardrail、provenance、dry-run summary、skipped reasons 与原有响应字段
- 本地验证通过：全量 pytest 58 项；lints 无新增问题

## v5.3.44 (2026-05-29) — 更多 AI 端点迁移
- `POST /api/ai-review/{job_id}`、`/api/ai-polish/{job_id}`、`/api/ai-abstract/{job_id}` 已迁入 `app/api/ai_routes.py`
- 新增轻量 helper 复用主 `.tex` 提取与 project directory 查找逻辑，减少 AI 路由重复代码
- 旧 `routes.py` 不再注册上述 AI 路径，避免重复路由和后续维护分叉
- 本地验证通过：全量 pytest 58 项

## v5.3.43 (2026-05-29) — AI 路由拆分起步
- 新增 `app/api/ai_routes.py`，开始把 AI 专属 API 从旧的全量 `routes.py` 拆出
- `POST /api/ai-diagnosis/{job_id}` 已迁入新路由模块，外部 API 路径保持兼容
- `app/main.py` 同时挂载 legacy API router 与 AI router，为后续逐步迁移保留小步提交空间
- 本地验证通过：全量 pytest 58 项

## v5.3.42 (2026-05-29) — Issue 详情折叠与 Evidence 搜索
- Issue 列表搜索现在会同时匹配 `evidence`，便于定位由 gate 提供的证据文本
- 长证据/建议默认折叠为“展开证据/建议”，展开区域限制高度并可滚动，避免撑爆右侧问题栏
- 短建议仍保持原有直接展示方式，减少对常见工作流的干扰
- 本地验证通过：前端 inline JavaScript 语法检查、全量 pytest 58 项

## v5.3.41 (2026-05-29) — 文件树搜索
- 工作台文件面板新增文件搜索框，可按文件名或路径快速过滤项目文件
- 文件树渲染拆出 `renderFileTree()`，保留原有目录分组、错误徽标和文件打开行为
- 搜索无结果时显示空状态，不影响当前已打开文件和 tab
- 本地验证通过：前端 inline JavaScript 语法检查、全量 pytest 58 项

## v5.3.40 (2026-05-29) — AI Loading 耗时显示
- 右下角 AI loading card 增加后台处理耗时秒表，长时间 LLM 请求时用户能确认任务仍在进行
- `hideAiLoading()` 会清理计时器，避免多次 AI 请求后残留 interval
- 保持 loading card 非阻塞行为不变，用户等待 AI 时仍可继续浏览和编辑
- 本地验证通过：前端 inline JavaScript 语法检查、全量 pytest 58 项

## v5.3.39 (2026-05-29) — Toast 去重与队列上限
- 前端 toast 增加 1.5 秒重复消息去重，避免网络错误、AI 请求失败或连续点击时刷屏
- 同屏最多保留 4 条 toast，新消息出现时会移除最旧提示，保持界面可读
- 保持原有 `toast(message, type, duration)` 调用方式不变，不影响现有上传、保存、AI 和报告流程
- 本地验证通过：前端 inline JavaScript 语法检查、全量 pytest 58 项

## v5.3.38 (2026-05-29) — LaTeX Cite/Ref 解析覆盖增强
- TeX parser 继续扩展真实论文常见引用命令：`smartcite`、`supercite`、`citeyearpar`、`citeposs`
- Ref parser 新增 `pageref`、`nameref`、`namecref`、`nameCref`、`cpageref`、`Cpageref` 覆盖，减少 cleveref/hyperref 论文误报
- 更新 parser 回归测试，确认扩展 cite/ref 命令能正确提取 key 且保持顺序
- 本地验证通过：parser 测试 16 项、全量 pytest 58 项

## v5.3.37 (2026-05-29) — AI 输出证据与可信边界
- AI 审稿模拟 prompt 明确标注“模拟审稿意见”，新增 Action Items，并要求证据不足时说明“论文片段中未看到证据”
- Abstract 优化 prompt 增加 claim consistency guard，禁止夸大正文片段中没有支持的实验结果、数字、贡献或 SOTA claim
- 官方 Checklist 生成要求每项返回 `evidence`，对缺失项返回 `missing_type` 和 `rewrite_suggestion`
- Checklist 前端展示证据、缺失类型和补写建议，并支持一键复制 Markdown 版清单
- 本地验证通过：前端 inline JavaScript 语法检查、Checklist/AI 专项测试 11 项、全量 pytest 58 项

## v5.3.36 (2026-05-29) — AI 论文诊断报告前端
- Overview 操作区新增「诊断报告」入口，工作台「AI 助手」下拉菜单新增「论文诊断报告」
- 新增诊断报告弹窗，展示核心摘要、先改哪三处、预计修改时间、快速收益、风险提示和下一步行动
- 诊断报告支持复制 Markdown，便于发送给导师或合作者；也可一键进入工作台处理问题
- 弹窗明确标注 AI 诊断仅供参考，并提醒人工核实科学结论、数字和引用
- 本地验证通过：前端 inline JavaScript 语法检查、全量 pytest 58 项

## v5.3.35 (2026-05-29) — AI 论文诊断报告接口
- 新增 `/api/ai-diagnosis/{job_id}`，基于 gate 摘要、top issues 和安全 metadata 生成结构化论文诊断
- 新增 `app/services/ai_reports.py`，集中处理诊断输入构建、JSON 解析和确定性 fallback，避免继续膨胀 routes 单体
- 诊断输入不会包含 `project_dir`、owner 信息或论文全文，只保留报告统计和问题摘要，降低敏感数据进入 LLM 的范围
- LLM 返回非 JSON、缺字段或调用失败时，会返回可展示的 fallback 诊断，不阻塞用户工作流
- 新增 AI integrity 回归测试，覆盖诊断 payload 脱敏、JSON fence 解析和 bad JSON fallback

## v5.3.34 (2026-05-29) — AI 批量建议按 Gate 分组
- AI 批量建议弹窗新增 dry-run 统计卡片，展示可修复数量、本次生成数量、生成上限和跳过项数量
- 批量建议按 gate 分组展示，每组可单独应用并只触发一次重新质检，全部应用也只重检一次
- 每条建议展示目标文件、行号、风险等级和 provenance，无法自动应用的建议不会显示应用按钮
- 弹窗支持复制 Markdown 版批量建议清单，方便发给导师或合作者人工核对
- 本地验证通过：前端 inline JavaScript 语法检查、AI integrity 测试 7 项、全量 pytest 55 项

## v5.3.33 (2026-05-29) — AI 批量建议 Dry-Run 摘要
- `/api/ai-batch-fix/{job_id}` 新增 dry-run `summary`，返回可修复总数、本次生成数、批量上限、按 gate 分组统计和跳过原因
- 批量建议候选收集改为可测试 helper，文献真实性、已忽略、缺文件、缺行号、空上下文、超出上限等情况不再静默跳过
- 每条批量建议补充 `gate_name`、`issue_index`、`can_apply`、`risk` 和 provenance，方便前端后续分组展示和审计
- 新增 AI integrity 回归测试，确认文献真实性问题不会进入 LLM 批量修复、已忽略问题会跳过、普通问题会保留 gate/issue/context 信息

## v5.3.32 (2026-05-29) — AI 助手前端入口补齐
- 总览页操作区新增「🤖 模拟审稿」按钮，可直接调用 AI 审稿接口查看结构化反馈
- 工作台工具栏新增「🤖 AI 助手」下拉菜单，统一收纳「模拟审稿 / 优化 Abstract / AI 批量建议」入口
- 写作质量问题中若命中 abstract 相关提示，会出现「✨ 优化 Abstract」快捷按钮，减少来回切换
- 新增 `runAiReview()` 与 `optimizeAbstract()` 前端交互闭环：支持结果弹窗、复制建议、Abstract 一键替换当前文件并自动保存

## v5.3.31 (2026-05-29) — 上传 ZIP 签名与宏文件防护
- 上传接口在写入磁盘前校验 ZIP magic bytes，即使文件名是 `.zip`，内容不是有效 ZIP 也会拒绝
- ZIP 解压危险扩展名列表扩展到 `.jar/.vbs/.js/.scr/.com` 与 Office macro 文件 `.docm/.xlsm/.pptm`
- 新增上传内容签名回归测试，确认伪装成 ZIP 的非 ZIP 内容被拒绝
- 扩展 ZIP 安全测试，确认宏文件会被跳过，不会落入解压目录

## v5.3.30 (2026-05-29) — 安全响应头与兼容 CSP
- 新增 FastAPI security headers middleware，所有响应默认带 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy` 和基础 `Permissions-Policy`
- 新增兼容当前单页应用的 Content-Security-Policy：限制 `object-src`、`base-uri`、`frame-ancestors`、`form-action`，同时允许现有 Tailwind/CodeMirror CDN 与 inline 脚本样式
- 增加安全响应头回归测试，确认首页响应包含 CSP、anti-clickjacking 与 nosniff 保护

## v5.3.29 (2026-05-29) — 文件树与 Tab 事件委托
- 文件树项和编辑器 tab 移除 inline `onclick`，改为 `data-action` / `data-path` + 全局 click 事件委托
- tab 关闭按钮改为 `data-action="close-tab"`，继续阻止事件冒泡，行为保持一致
- 进一步缩小用户上传文件路径进入 JavaScript handler 的范围，为后续逐步移除剩余 inline event 打基础

## v5.3.28 (2026-05-29) — AI Guardrails 服务模块抽取
- 新增 `app/services/ai_guardrails.py`，集中管理 reference authenticity 判定、not-fixable payload、AI provenance、reference title 提取和候选元数据转换
- `app/api/routes.py` 删除对应 helper 定义并改为引用服务模块，减少路由文件职责，保持现有 API 和测试导入兼容
- 为后续继续拆分 AI routes / reference candidate service 打基础

## v5.3.27 (2026-05-29) — 前端 API 错误处理统一化
- 新增 `apiFetch()` 前端请求包装器，自动携带 share token、检查 HTTP 状态，并把 401/402/403/404/409 转成明确用户提示
- 工作台核心 API 调用改用 `apiFetch()`：状态轮询、报告加载、文件树、文件打开/保存、重新质检、忽略问题、导出报告、删除项目、历史列表和 AI 跨文件写入
- 重新质检增加 try/catch/finally，失败时恢复按钮状态并展示错误，不再卡在“检查中...”
- 文件保存/打开/跨文件 AI 写入失败会保留错误状态并返回失败，减少静默失败和误提示成功

## v5.3.26 (2026-05-29) — 写作质量检查正文层降噪
- WritingQualityGate 新增 lightweight text layer，写作启发式分析会排除 LaTeX comments、bibliography/thebibliography、verbatim、lstlisting、minted 等非正文区域
- AI 痕迹、套话、段落重复、拼写等文本启发式改为基于正文层运行，减少注释、参考文献或代码块触发误报
- `[final]` 模式、author、hypersetup、LaTeX 命令拼写等结构性检查仍基于原始 LaTeX，避免漏掉模板/命令问题
- 新增回归测试，确认注释和 bibliography 中的 AI marker 不会触发写作质量 error

## v5.3.25 (2026-05-29) — 引文验证缓存与临时故障降级
- ReferenceAuthenticityGate 增加 DOI 和标题搜索的进程内轻量缓存，避免同一批检查反复请求 Crossref / DataCite / Semantic Scholar / OpenAlex
- DOI 解析区分“确实未找到”和“外部 provider 超时/429/5xx 暂不可用”；后者降级为 warning `verification_unavailable`，不再把网络波动误判为 fake reference
- 标题搜索结果也进入缓存，减少无 DOI 文献的重复外部检索
- 新增引文验证韧性测试，覆盖成功 DOI 缓存和 provider 临时失败不产生 error 的行为

## v5.3.24 (2026-05-29) — 健康检查与部署就绪探针
- 新增 `/healthz` liveness probe，返回服务名和当前版本，用于本地演示和容器健康检查
- 新增 `/readyz` readiness probe，检查数据库、加密后端、LLM 配置、支付 sandbox 生产风险、上传/数据目录状态
- `/readyz` 只返回布尔值和状态摘要，不暴露 API key、Bearer token 或内部 LLM endpoint
- 配置新增 `APP_ENV` / `settings.app_env`，生产环境下会把 `PAYMENT_SANDBOX=true` 标记为 degraded
- 新增健康检查回归测试，确认 liveness 可用且 readiness 不泄露 secret 模式

## v5.3.23 (2026-05-29) — 前端 inline handler 参数注入加固
- 新增 `jsArg()`，所有动态 inline handler 参数统一通过 JSON string literal 编码，避免文件名、issue message、job_id 中的引号或特殊字符破坏 JavaScript
- 加固文件树、编辑器 tab、overview 问题跳转、问题卡片、AI 建议按钮、忽略按钮、真实文献候选、历史项目/所有项目恢复与删除入口
- 文件树 `data-path`、tab 文件名等动态内容补充 HTML escape，降低用户上传文件名造成 XSS/DOM 注入的风险

## v5.3.22 (2026-05-29) — FileStore 服务抽取
- 新增 `app/services/file_store.py`，集中管理项目内安全路径解析、可编辑文件列表和当前项目 ZIP 打包
- `app/api/routes.py` 改用 FileStore helper，减少 routes 单体职责，文件读取/保存、文件树和下载 ZIP 共享同一套路径安全逻辑
- 新增 FileStore 单元测试，覆盖路径穿越拦截、LaTeX 支撑文件列表和 ZIP 相对路径保留
- 本地验证通过：ruff、JS syntax check、pytest 45 项

## v5.3.21 (2026-05-29) — Release Checklist 与 CI Secret Scan 修正
- 新增 `docs/RELEASE_CHECKLIST.md`，固定每次发布/备份前的 changelog、版本、JS、pytest、secret scan、git status、提交推送和本地重启检查步骤
- 修正 CI secret scan，排除 workflow 文件自身，避免扫描规则中的敏感模式字符串触发自检失败
- 将 ARR / NeurIPS 官方 checklist 模板从 `app/api/routes.py` 抽到 `app/checklists.py`，减少路由上帝文件体积，并为后续扩展 venue-specific 模板铺路
- 新增 checklist 模板回归测试，锁定 ARR `A1-E1` 18 项和 NeurIPS `1-16` 16 项

## v5.3.20 (2026-05-29) — CI 扩展与 Ruff 清理
- GitHub Actions CI 增加 Node 环境、前端内联 JavaScript 语法检查、敏感信息扫描和统一 `python -m pytest -q`
- 本地修复现有 ruff `E/F/W` 问题，清理未使用导入、无占位 f-string、含糊变量名和 docstring 转义警告，确保新增 CI 不会一上线就失败
- CI 增加 `pytest-cov` coverage 门槛和 `pip-audit` 依赖审计；secret scan 扩展覆盖 `Bearer sk-`、`LLM_API_KEY=`、`LLM_BASE_URL=` 等高风险模式
- `pyproject.toml` 与运行依赖对齐，补入 SQLAlchemy、aiosqlite、bcrypt、PyJWT，并将 pytest-cov / pip-audit 加入 dev 依赖
- 新增 `docs/RELEASE_CHECKLIST.md`，固化每次更新前的 changelog、版本号、测试、secret scan、提交和 push 备份流程
- 本地验证通过：ruff、JS syntax check、pytest 41 项

## v5.3.19 (2026-05-29) — 只读分享链接与修复包下载
- 工具栏新增「分享」按钮，复制包含 `share_token` 的导师只读链接；通过分享链接打开页面时会自动携带 token 加载报告、状态、文件树和导出
- 新增 `/api/download/{job_id}`，可下载当前编辑后的项目 ZIP，保留目录结构，供作者提交或备份修复版本
- 工具栏新增「下载 ZIP」按钮，直接下载当前修复后的项目包
- 分享 token 保持只读：可查看报告/文件/导出/下载 ZIP，但不能保存、重检、忽略问题或调用工具/AI
- 新增下载 ZIP 分享权限回归测试

## v5.3.18 (2026-05-29) — 前端弹窗与文件树体验加固
- 新增前端 `showModal()`、`safeUrl()` 和 ESC 关闭顶层弹窗能力，减少重复 modal 代码并避免不安全 URL 直接进入链接
- 真实文献候选弹窗改用统一 modal helper，候选来源 URL 经过协议白名单过滤，仅允许 http/https/mailto
- 文件列表 API 与保存 API 对齐，文件树现在会列出 `.cls/.sty/.bst/.txt/.md` 等可编辑 LaTeX 支撑文件，不再只能看到 `.tex/.bib`
- 切换/恢复不同 job 时统一清空工作台状态（当前文件、打开 tabs、错误高亮、问题列表、编辑器内容），避免显示或保存上一份论文
- 切换文件前会 flush 待执行的自动保存，降低 800ms debounce 未完成导致修改丢失的风险
- 文件读写 API URL 按路径分段编码，支持空格、中文、`#`、`?` 等文件名字符；保存失败会显示错误并保留红色状态
- 新增文件树回归测试，确认 `.sty` 等支持文件会展示在编辑器文件列表中

## v5.3.17 (2026-05-29) — Job 状态持久化与并发保护
- 上传/重新质检中的 job 增加内存锁，阻止同一 job 重复触发并发 recheck，避免多个后台任务同时写同一目录和报告
- 后台检查失败时生成并持久化 failed report，保存脱敏错误摘要、owner/share metadata 和 `status=failed`，服务重启后可恢复失败状态
- 从磁盘恢复 report 时优先读取 `metadata.status`，不再把所有已落盘 report 都强制视为 completed
- 新增 job 状态持久化回归测试，覆盖 failed report 的状态、owner metadata 与错误摘要保存

## v5.3.16 (2026-05-29) — AI 建议应用改为可审计 Diff 视图
- AI 单条建议弹窗改为原文片段 / AI 建议片段双栏展示，并显示风险等级和 provenance 来源信息
- 只有后端返回可替换原文时才显示「采用建议并重新质检」按钮，避免无锚点建议被直接应用
- 精确匹配失败时不再把建议插入光标处，改为提示用户复制后人工核对，避免“瞎替换”或插错位置
- 补充 AI integrity 测试，确认文献真实性问题不返回 suggestion，普通非文献问题仍可走 AI 建议

## v5.3.15 (2026-05-29) — LaTeX/BibTeX 解析准确性增强
- LaTeX citation parser 支持更多 natbib/biblatex 命令与 optional args，包括 `citealt/citealp/citeauthor/citeyear/parencite/textcite/autocite/footcite/nocite`
- reference parser 支持 `subref/vref/Vref/crefrange/Crefrange` 和 comma-separated cleveref 引用，减少真实论文中的漏检
- BibTeX DOI 解析统一规范化 URL、`doi:` 前缀、LaTeX 转义下划线和尾部标点，减少 DOI 误判
- 结构检查支持 biblatex `\addbibresource{}` 和 `\graphicspath{{...}}`，并能匹配省略扩展名的图片路径
- 新增 parser/gate 回归测试，覆盖扩展 citation/ref、DOI 规范化、graphicspath 和 addbibresource

## v5.3.14 (2026-05-29) — AI 建议可信度与真实文献候选
- AI 单条/批量建议返回 `risk`、`requires_manual_review` 和 `provenance` 审计信息，标明模型、gate、文件、行号和上下文长度
- 文献真实性问题统一返回 `not_fixable` 高风险响应，并声明可走候选搜索，不调用 LLM 生成替换文献
- 新增 `/api/reference-candidates/{job_id}`，只从 Crossref / Semantic Scholar / OpenAlex 检索真实候选，返回来源、标题、作者、年份、DOI/URL；该接口不使用 LLM
- 前端文献真实性问题显示「查找真实候选」按钮，候选弹窗提示必须人工核对后再替换，并可继续获取官方 Bib
- AI 建议修复弹窗改为原文/建议双栏 diff 预览，显示风险与 provenance；无法精确匹配原文时不再把建议插入光标位置，避免误写文件
- 新增 AI integrity guardrail 测试，覆盖 not-fixable payload、标题提取和 Crossref 候选元数据转换

## v5.3.13 (2026-05-29) — Auth 与支付安全补强
- 登录/注册实际接入 IP+邮箱维度限流，防止暴力尝试；认证 cookie 会在 HTTPS/生产环境自动启用 `Secure`
- 新增 `payment_orders` 数据库表，支付订单不再只依赖内存；订单状态查询优先读取数据库
- 支付回调增加幂等入账、金额校验和 Alipay `app_id` 校验，同一订单重复回调不会重复加积分
- 管理员充值改为 `Authorization: Bearer ...` 或 `X-Admin-Key` header 鉴权，并增加基础限流；不再接受 body 中的 `admin_key`
- 新增 auth/payment 安全测试，覆盖登录限流、HTTPS cookie、管理员 header key、支付回调幂等

## v5.3.12 (2026-05-29) — ZIP 上传安全强化
- ZIP 解压前新增 metadata 预扫描，限制成员数量、总未压缩大小、单文件大小、目录深度和异常压缩比，阻断 zip bomb / zip flood / 极深路径滥用
- 拒绝 ZIP 内 symlink 条目和规范化后重复路径，继续保留 Zip Slip 防护与危险可执行文件跳过逻辑
- 解压过程中任何安全校验或写入失败都会清理半成品目录，避免残留不完整项目文件
- 新增 ZIP 安全回归测试，覆盖路径穿越清理、过多文件、可疑压缩比、过深路径和 symlink

## v5.3.11 (2026-05-29) — 质检结果页移除模拟审稿入口
- 从质检结果概览页移除「模拟审稿人反馈」按钮、反馈展示卡片和通过态中的审稿反馈提示；后端 AI 审稿接口保留，便于后续移动到提交区域

## v5.3.10 (2026-05-29) — 精简后台处理提示
- 将 AI 进度浮窗副文案精简为「后台处理中...」，去除后半句说明，避免页面提示过长

## v5.3.9 (2026-05-29) — Job Owner 与分享权限隔离
- 新增匿名 `sl_session` httpOnly cookie、登录用户/匿名 session owner 元数据，以及只读 `share_token`；新上传任务会在报告 metadata 中持久化 owner/share 信息
- 所有 job/file/report/tool/AI 相关 API 接入统一读写校验，分享 token 仅允许只读访问报告、状态、导出和文件读取，不能保存、重检、忽略问题或调用工具/AI
- 历史、对比、趋势列表按当前 owner 过滤；旧报告缺少 owner metadata 时继续兼容本地演示访问

## v5.3.8 (2026-05-29) — 精简上传页免责声明
- 删除上传页底部免责声明中“AI 给出的是修改建议，请人工核实后再采用；切勿依赖 AI 生成或替换参考文献”这句重复文案，保留检查结果/AI 建议仅供参考与以官方要求为准的说明

## v5.3.7 (2026-05-29) — 顶部品牌中文标识放大
- 左上角 logo 旁的「投稿通」从小徽标调整为更醒目的 16px 加粗中文品牌标识，与 `ScholarLint` 并列时更容易被注意到

## v5.3.6 (2026-05-29) — 官方 ARR / NeurIPS Checklist 对齐
- **ARR Responsible NLP Research Checklist**：按官方页面 `https://aclrollingreview.org/responsibleNLPresearch/` 对齐 A-E 维度与 A1-E1 问题，包括 limitations、risks、scientific artifacts、computational experiments、human annotators/participants、AI assistants
- **NeurIPS Paper Checklist**：按官方页面 `https://neurips.cc/public/guides/PaperChecklist` 对齐 1-16 项，包括 claims、limitations、theory/proofs、reproducibility、code/data、experimental details、statistics、compute、ethics、broader impacts、safeguards、licenses、assets、human subjects、IRB、LLM usage
- 前端「复现清单」改为先选择 ARR 或 NeurIPS；生成结果显示官方 checklist 名称、来源链接、section 分组和 yes/no/n/a 统计
- 后端 `/api/venue-checklist/{job_id}` 支持 `venue=arr` / `venue=neurips`，不再使用旧的自定义 C/D/E/T 泛化清单

## v5.3.5 (2026-05-29) — 文献真实性问题不再提供 AI 建议
- **彻底禁用文献错误的 AI 建议修复**：`reference_authenticity` gate 以及「缺少 DOI / 无可信来源 / 标题搜索未找到 / Unverified reference / source not found」等文献真实性问题不再显示「AI 建议修复」按钮，改为「需人工核实文献」
- **后端双重防护**：即使直接调用 `/api/ai-fix`，上述问题也返回 `not_fixable`，不会生成 BibTeX 或任何替换片段；`/api/ai-batch-fix` 也跳过这些问题
- 目标：避免 AI 为假文献、缺失 DOI、无法验证来源的文献编造另一个看似真实的假引用。后续如做推荐，只能基于 Crossref / Semantic Scholar / OpenAlex 等权威候选结果，再让 AI 判断相似度，不能凭空生成

## v5.3.4 (2026-05-29) — AI 进度提示改为右下角非阻塞浮窗
- **AI 建议修复/AI 功能进度不再阻塞页面**：将原先全屏 loading overlay 改为右下角浮动进度卡片（`pointer-events:none`），用户等待 AI 返回时仍可正常浏览、编辑、点击页面
- 进度文案调整为「后台处理中，可继续浏览和编辑…」，降低等待焦虑，同时不打断工作流

## v5.3.3 (2026-05-29) — AI 定位为"建议"+ 免责声明 + 应用后自动重检
- **措辞改为"建议"**：「AI 修复」→「AI 建议修复」、「一键修复」→「AI 批量建议」、批量弹窗标题→「AI 批量建议修复」、单条弹窗→「AI 建议修复」；应用按钮→「采用建议并重新质检」/「全部应用并重新质检」，强调 AI 只给建议、需人工核实
- **免责声明**：上传页底部新增完整免责 footer，总览页底部新增精简版；AI 建议弹窗（单条/批量）内加显著免责提示
- **应用后自动重新质检**：采用任意 AI 建议（单条 `applySingleFix` / 单个 `applyBatchFix` / 全部 `applyAllBatchFixes`）后自动调用 `doRecheck()`，确保结果即时反映改动、避免"改完没复核"

## v5.3.2 (2026-05-29) — 学术诚信护栏：AI 不再为假文献编造替换
修复严重问题：之前 AI 修复会把"伪造/无法验证的文献"替换成**另一个编造的假文献**。
- **批量修复跳过 `reference_authenticity` gate**：引文真实性问题绝不自动修复（自动替换 = 再造一个假引用）
- **单条 AI 修复对引文真实性问题返回"建议"而非生成**：提示作者删除或用真实可查的文献替换，并引导使用『📥 获取官方 Bib』，不编造任何条目（前端以告示弹窗呈现，无"应用"按钮）
- **新增判定** `_is_reference_authenticity_issue`（按 gate 名 + 精准关键词）；前端「AI 修复」按钮现传入 gate 名
- **所有修复提示词加禁令**：绝不编造文献信息（作者/标题/期刊/年份/DOI/页码），无法确定时保持原样或留占位
- 实测：假文献 `[fake_entry_1] DOI 无法解析` → ai-fix 返回建议、batch-fix 不纳入

## v5.3.1 (2026-05-29) — AI 批量修复内容可滚动
- **修复批量修复弹窗内容看不全**：每条"原文/修复"框原为 `max-height:80px; overflow:hidden`（被裁剪），改为 `max-height:220px; overflow:auto`（可滚动），并加 `word-break:break-word` 让 DOI 等长串自动换行，可查看完整内容

## v5.3.0 (2026-05-29) — 正规加密：密钥/数据/模型用量全面加固
全面保护 API key、数据与模型调用。

### 密钥加密存储（at-rest）
- 新增 `app/secrets_manager.py`：密钥以 **Fernet（AES-128-CBC + HMAC）** 加密存于 `data/secrets.enc`；**主密钥存于操作系统凭据库**（Windows 凭据管理器 / DPAPI，经 `keyring`），绑定当前账户，绝不明文落盘
- 新增 `app/secrets_setup.py` 迁移工具：`python -m app.secrets_setup` 把 `.env` 与旧明文密钥迁入加密库并**删除明文**（`.env`、`data/.jwt_secret`、`data/.admin_key` 已删除）
- `config.py` 改为从加密库解析（环境变量优先 > 加密库），LLM key / endpoint / JWT / admin / 支付密钥全部走加密库
- `.gitignore` 增加 `data/secrets.enc`、`.env.*`

### 日志/错误脱敏
- 新增 `secrets_manager.redact()`：任何日志或 API 错误返回中出现的 key / endpoint 一律替换为 `***REDACTED***`
- 已接入全局异常处理器、LLM 服务、6 个 AI 接口的错误返回、质检/重检失败日志

### 模型用量上限（防滥用 / 控成本）
- 新增 `_llm_usage_guard`：所有 6 个 AI 接口加 **按 IP 限流**（默认 30 次/小时）+ **全局每小时上限**（默认 500 次），超限返回 429；阈值可经环境变量覆盖（`LLM_RATE_PER_IP` / `LLM_RATE_WINDOW` / `LLM_GLOBAL_HOURLY_CAP`）

### 数据静态加密
- 质检报告改为加密存储 `data/jobs/{id}.enc`（Fernet），兼容读取旧 `.json` 并在下次保存时迁移；加密栈不可用时回退明文
- 上传 zip 解压后即删除（原已实现）；解压出的工作文件因需实时编辑/质检仍为明文，7 天自动清理（已知限制）

### 依赖
- 新增 `cryptography`、`keyring`

## v5.2.15 (2026-05-29) — 修复 AI 单条修复"瞎替换"
- **根因**：`applyAiFix` 按"问题行号 ±2 行"盲目替换，而后端给 AI 的上下文是 ±5 行，区域不匹配 → 替换错行、留下残行
- **后端**：`/ai-fix` 现在同时返回它发给模型的**原始上下文** `original` 与 `file`；并强化提示词要求 AI 返回**完整**修复片段（保留未改动行），以便整体替换
- **前端**：新增 `applySingleFix()`，复用稳健的 `applyOneFix`（行尾归一化 / 去 markdown 围栏 / `$` 安全替换 / 跨文件）按原文**精确定位替换**；定位失败时**不再盲目覆盖**，而是在光标处插入并提示手动核对
- 实测：ai-fix 正确返回 original + file，应用后精确替换对应片段

## v5.2.14 (2026-05-29) — 统计数据并入分数行
- **错误/警告/引文/词数 移到 xx/100 分数旁边**：不再单独占一行，分数与四项统计在同一行水平排列（`flex` + `flex-wrap`，窄屏自动换行），总览更紧凑

## v5.2.13 (2026-05-29) — 总览精简：去趋势/对比/评分，卡片对齐
- **移除分数趋势**（📈 分数趋势）区块与 `loadScoreTrend()` 调用
- **移除"较上次: X 分"对比**（`loadComparison()` 不再调用）
- **移除字母评分徽章**（A/B/C/D），分数区只保留 `xx/100` 与状态文案
- **6 个 gate 卡片对齐**：总览卡片网格由自适应 + 顶部对齐改为固定两列 + 等高对齐（`repeat(2,minmax(0,1fr))` + `align-items:stretch`），不再参差不齐

## v5.2.12 (2026-05-29) — 投稿清单改为 Reproducibility Checklist
- **ARR/NeurIPS → Reproducibility Checklist**：将原会议清单（ACL ARR / NeurIPS 二选一）替换为统一的「复现性清单」，更聚焦论文可复现性
- **后端**：用 `REPRODUCIBILITY_CHECKLIST`（15 项，分 Code & Models / Datasets / Experimental Results / Theoretical Claims 四类）替换 `ARR_CHECKLIST`、`NEURIPS_CHECKLIST`；`/api/venue-checklist` 不再需要 venue 参数，system prompt 改为复现性助手并更新示例
- **前端**：工具栏按钮由「ARR/NeurIPS」改为「复现清单」，去掉会议二选一弹窗、直接生成；结果弹窗标题固定为「Reproducibility Checklist」
- 实测：上传 → 完成质检 → 生成复现清单，AI 正确返回 15 项 yes/no/na + 可粘贴理由

## v5.2.11 (2026-05-29) — AI 加载遮罩 + 总览交互/文案优化
- **AI 加载遮罩**：调用任意 AI 功能（ai-fix / batch-fix / review / polish / abstract / venue-checklist）时显示一个持续的加载遮罩（带转圈动画），直到 AI 返回（成功或失败）才消失，给用户明确预期；统一 `showAiLoading()` / `hideAiLoading()`，各 AI 函数以 try/finally 包裹确保关闭
- **总览问题可点击跳转**：质检结果总览中每条错误预览均可点击，点击后进入工作台、自动打开对应文件并跳转高亮到对应行（新增 `gotoIssueFromOverview()`）；"还有 N 个错误"也可点击进入工作台
- **总览改两栏布局**：gate 卡片由单列改为自适应两栏（`minmax(300px,1fr)`，窄屏回退单列），更易浏览；顶部统计条仍整行展示
- **上传框文案**：将"🔒 文件加密保留 7 天，到期自动清理"移入上传拖拽框内；删除"上传后自动执行 6 项检查：…"这句冗余说明
- **"所有项目"入口补全**：在首页"最近的检查"标题旁补上「所有项目 →」按钮，触发 v5.2.10 已实现但缺少入口的全部项目弹窗

## v5.2.10 (2026-05-29) — 首页"最近的检查"精简 + 所有项目入口
- **首页只展示最近一次检查**：上传页历史区由原先列出最近 5 条改为仅显示「最新一条」检查记录，界面更聚焦
- **新增"所有项目"入口**：历史区标题旁新增「所有项目 →」按钮，点击弹出模态框（与批量修复 / 投稿清单等模态风格一致）列出全部检查记录（文件名、日期、得分、通过门数），可点击任意项恢复查看（复用 `resumeJob`）或删除（`deleteJobInModal`，删除后同步刷新首页与列表）
- 保持原有清爽卡片设计（slate 配色、圆角），移动端自适应；空历史时历史区仍隐藏，恢复/删除等既有流程不变

## v5.2.9 (2026-05-29) — 上传页 hero 品牌文案调整
- **首页 hero 主副标题对调**：上传页（`#screen-upload`）左侧品牌区将大标题由 `ScholarLint` 改为 `投稿通`，下方副标题由 `投稿通 · Academic Paper Pre-submission Checker` 改为 `ScholarLint · 为你的投稿保驾护航`
- 仅替换文案内容，保留原有字号、字重、颜色等样式；不影响左上角导航栏品牌

## v5.2.8 (2026-05-29) — 刷新保持当前视图（不再回到首页）
- **修复"刷新一直回到首页"**：之前刷新浏览器总是重置到上传页，丢失正在查看的报告
- **状态持久化到 URL**：进入概览/工作台或打开任务时通过 `history.replaceState` 写入 `?job=<id>&view=overview|workspace`（保持链接可分享），并同步写入 `localStorage`（`sl_lastJob`/`sl_lastView`）作为兜底
- **加载时恢复**：页面初始化优先从 URL 读取 `job`/`view`（缺失时回退 localStorage），自动加载该任务报告并恢复到原来所在的概览或工作台界面
- **优雅兜底**：任务已删除/不存在（报告加载失败，如 404）时清除过期状态并回到上传页；点击"返回首页"/品牌名/删除任务（`showScreen('screen-upload')`）也会清除持久化状态，确保之后刷新停留在上传页
- 兼容既有 `?job=` 分享链接、历史记录 `resumeJob` 与全新上传流程

## v5.2.7 (2026-05-29) — 模块化检查标题文案优化
- **模块化检查能力区块文案调整**：删除副标题 `每个模块独立运行，精准定位论文问题`（连同其独立的 `<p>` 元素一并清理），并将该区块主标题由 `模块化检查能力` 改为 `模块化检查，精准定位文章问题`，使标题直接传达定位价值

## v5.2.6 (2026-05-29) — 顶部左上角品牌名放大
- **左上角导航栏品牌更醒目**：持久导航栏的 `ScholarLint` 字号由 14px 提升至 20px、字重由 700 提升至 800；旁边的盾牌 logo 图标由 28×28 放大至 34×34（内部 emoji 14px→18px），`投稿通` 角标由 9px 微调至 11px。仅调整左上角导航栏品牌，上传页 hero 大标题保持不变；导航栏高度 48px 不变，移动端布局不受影响

## v5.2.5 (2026-05-29) — 问题按文件正确归属 + 整理后自动质检
- **修复"每个文件都被标了问题"**：`issueMatchesFile` 之前把任意 `.tex` 问题匹配给所有 `.tex` 文件。现改为优先按 `issue.file`（文件名）精确归属，bib 问题归 `.bib`，其余按 location 中的文件名匹配；全局/跨文件问题不再误标到每个文件
- **整理结构后自动重新质检**：`executeTidyUp` 执行完改动后自动调用 `doRecheck()`，无需手动再点"重新质检"

## v5.2.4 (2026-05-29) — 整理结构精简 + 文件树显示文件夹
- **整理结构**改为只抽取表格到 `floats/`：移除图片环境抽取与图片文件移动（图片保持原位）
- **文件树按文件夹分组展示**：之前是按类型平铺、只显示文件名，看不到 `floats/`、`sections/` 等目录；现按真实目录结构分组（根目录 + 各子文件夹，带缩进），整理后新建的 `floats/` 立即可见

## v5.2.3 (2026-05-29) — AI 修复"无法匹配原文"修复
修复 AI 批量/单条修复应用失败的多个叠加 bug：
- **行尾符**：Windows 文件为 CRLF，编辑器为 LF，导致 `includes()` 永远匹配不到原文 → 应用前统一规范化为 LF
- **markdown 围栏**：AI 返回的 ```latex ... ``` 会被插进 `.tex` → 前后端都剥离围栏（新增后端 `_strip_code_fence()` + 前端 `stripFences()`）
- **跨文件**：编辑器只持有当前文件，修复若针对其它文件则匹配失败 → 按 `fix.file` 自动读取/写回目标文件
- **`$` 转义**：用替换函数应用修复，避免 LaTeX 数学环境的 `$` 被 `String.replace` 当成特殊序列
- 应用成功后刷新文件树状态

## v5.2.2 (2026-05-29) — AI 修复跟随论文语言
- 修复 AI 修复建议（`/ai-fix`、`/ai-batch-fix`）对英文论文输出中文的问题
- 新增 `_detect_lang()` 语言检测（按上下文 CJK 占比判定 zh/en）
- 英文论文 → 强制英文修复（明确禁止插入中文）；中文论文 → 中文修复
- 实测：英文 figure 未引用问题现在返回正确的英文 `\ref` + figure 块

## v5.2.1 (2026-05-29) — 默认模型切换 gpt-5.2
- 默认模型由 `gpt-5.5` 改为 `gpt-5.2`：更快（1.6–2.5s vs ~2.3s+）、成本更低
- gpt-5.2 非推理模型，原生支持 `temperature`，实测 V2 key + SGP endpoint 可用
- 仅改默认值与 `.env`，无需改动统一 LLM 调用层（仍兼容推理/非推理模型）
- 安全清理：用 git-filter-repo 从全部历史中移除已失效的旧密钥（V1 key / 旧 JWT / 旧 admin key），强制推送覆盖远程；清洗前已完整备份（bundle + mirror）
- **base_url 也视为敏感信息**：从 `config.py` 移除硬编码的公司 endpoint 默认值（改为仅从 `.env` 读取），并再次清洗历史，移除全部公司 LiteLLM endpoint（`REMOVED_HOST` / `REMOVED_HOST`）

## v5.2.0 (2026-05-29) — 公司内网 LLM 接入 + 修复
打通 LLM 全流程，改用公司内网 LiteLLM（UXBench）API，并修复阻断质检的 bug。

### LLM 接入（密钥隔离）
- API key 改为仅从 `.env` / 环境变量读取，`config.py` 不再硬编码任何 key（`config.py` 受 git 跟踪，硬编码会泄露）
- 新增 `.env`（已 gitignore，永不入库）承载公司 endpoint / key / 默认模型
- 默认模型切换为 `gpt-5.5`（V2 key + SGP endpoint），V1 key 已过期
- 启动时通过 `python-dotenv` 自动加载 `.env`；新增 `python-dotenv`、`openai` 显式依赖
- **兼容推理模型**：`gpt-5.5` 等拒绝非默认 `temperature`，新增统一 LLM 调用层（`llm_check` + `_llm_chat_post` 共享 helper），遇到 `temperature` 报错自动去参重试；空 `content` 回退 `reasoning_content`
- 全部 6 个 AI 接口（ai-fix / ai-batch-fix / ai-review / ai-polish / ai-abstract / venue-checklist）改走统一 helper，对模型无感

### Bug 修复
- 修复 `gate_references._check_citation_freshness` 中 `entry.fields` 属性错误（`BibEntry` 无 `fields`），此前会导致引文新鲜度检查抛异常、**整个质检流程 failed**。改用 `entry.year`，回退 `raw_fields`

### 验证
- 端到端实测：上传 → 6 个 gate 全部完成（score 80）→ AI 审稿模拟返回真实反馈，全程使用公司 API
- 16 个单元测试通过

## v5.1.0 (2026-05-29) — 安全加固 Security Hardening
重点：在不改变任何已有功能/设计的前提下，修复一批安全问题，并补齐加固中遗留的缺陷。

### 密钥与配置
- 所有敏感配置改为优先从环境变量读取（`LLM_API_KEY` / `JWT_SECRET` / `ADMIN_KEY` / 支付宝密钥 / `PAYMENT_SANDBOX`）
- **JWT secret / admin key 持久化**：未设置环境变量时，自动生成并写入 `data/.jwt_secret`、`data/.admin_key`（权限 0600）。修复了此前 `os.urandom()` 默认值导致每次重启都失效、用户全部被登出的回归问题
- 管理员充值接口的 admin_key 不再硬编码，改为从 `settings.admin_key` 读取
- 新增 `.gitignore` 条目，确保密钥文件永不入库

### 上传与文件安全
- **Zip Slip 路径穿越防护**：解压前逐条校验成员路径，越界即拒绝（组件级 `relative_to` 校验，修复 `startswith` 绕过漏洞）
- **危险文件过滤真正生效**：改为逐个解压成员，跳过 `.exe/.sh/.bat/.cmd/.ps1/.dll/.so/.bin/.msi`（此前 `extractall` 会忽略过滤、解压全部文件）
- 上传增加 `Content-Length` 预检（100MB），避免读入超大请求体
- 文件保存接口限制为文本源文件白名单（`.tex/.bib/.cls/.sty/.bst/.txt/.md`），阻止写入二进制/可执行文件，同时保留 `.cls/.sty` 等的正常编辑能力
- format-normalize 接口增加路径穿越校验

### 认证
- 登录/注册增加内存级限流（5 分钟内 10 次），防暴力破解
- 注册邮箱改用 `EmailStr` 校验；新增 `email-validator` 依赖（此前缺失会导致应用无法启动）
- 登录/注册 Cookie 显式标注 `secure`（生产 HTTPS 下应置为 True）
- 用户 / 交易 / Job ID 从 8 位 UUID 提升到 12 位 hex（熵 32→48 bit）

### 前端 XSS
- `linkify` 先转义再生成链接，仅允许 http/https，并加 `rel="noopener noreferrer"`
- 引文 DOI 链接、写作建议 tips 渲染统一经 `esc()` 转义

### 测试
- 新增 ZIP 安全回归测试（危险文件跳过、路径穿越拦截），共 16 个单元测试全部通过

## v2.8 (2026-05-28)
- File tree error count badges (red number showing unresolved errors per file)
- Favicon (🛡️ emoji SVG, no more 404)
- Multi-paper management marked complete (history list serves this purpose)

## v2.7 (2026-05-28)
- 🤖 AI Fix button: LLM-powered fix suggestions (uses internal LiteLLM API)
- 🔗 Share link button (copies URL with ?job=xxx for advisor viewing)
- PDF metadata anonymization check (\hypersetup pdfauthor detection)
- CHANGELOG.md created with full version history

## v2.6 (2026-05-28)
- Share link functionality (?job=xxx auto-loads report)
- PDF metadata leakage detection
- CHANGELOG.md

## v2.5 (2026-05-28)
- Text-table number consistency check (detects "achieve 0.86" when table says 0.85)
- Global exception handler middleware (clean JSON error responses)
- Language polish suggestions (long sentences >50 words, passive voice overuse)
- CSS variables design system (:root with colors, radius, shadows)
- Issue card slideUp animation
- File security scanning (removes .exe/.sh, 100MB upload limit)

## v2.4 (2026-05-28)
- CSS variables design system
- Language polish: long sentence detection, passive voice warning
- Panel transition animations (slideUp for issue cards, fadeIn for screens)

## v2.3 (2026-05-28)
- White/light theme homepage (replaced dark gradient with clean white)
- Modular feature showcase section (6 cards: verification, bib, writing, data, figures, security)
- Fixed JS syntax error (extra closing brace)

## v2.2 (2026-05-28)
- Bib comparison modal (side-by-side before/after with Replace button)
- Line jump flash animation (blue pulse when clicking issue)
- Title matching relaxed (>=85% or substring = pass, 60-85% = warning not error)
- Unicode family name normalization (LaTeX diacritics like \"u → u)
- Anonymization: detects [final] vs [review] in ACL/EMNLP templates
- Removed aggressive "伪造" wording from suggestions
- File security: dangerous file removal + 100MB limit

## v2.1 (2026-05-28)
- Ctrl+S manual save with toast confirmation
- Page transition fadeIn animation (0.25s)
- Editor right-click context menu (jump to issue, recheck, save, tidy bib, export)
- Network error graceful handling (toast instead of crash)
- Line counter shows Ln X/Total
- Overview "Top issues" summary box (top 5 errors highlighted)

## v2.0 (2026-05-28)
- Right-click context menu in editor
- Page transition animations
- Ctrl+S save shortcut
- Error state handling improvements

## v1.9 (2026-05-28)
- Editor dark theme toggle (material-darker + 🌙 button, persisted to localStorage)
- Auto-add \label quick-fix button for figure/table issues
- Reference verification detail panel (expandable on overview)
- Word count + page estimate in overview stats

## v1.8 (2026-05-28)
- Auto-add \label button for missing labels
- Word count and page estimate stats
- Reference verification expandable detail (per-entry status)
- Overview stats: errors, warnings, citations, words, pages

## v1.7 (2026-05-28)
- Word count / page estimate in report metadata
- Reference verification detail expandable panel
- Stats summary badges on overview

## v1.6 (2026-05-28)
- Overview stats summary (errors/warnings/citations/words/pages)
- Gate cards show warning count
- Overview cards clickable (jump to workspace)

## v1.5 (2026-05-28)
- One-click bib replacement (finds entry by DOI, replaces in editor)
- Browser notification when check completes (if tab is hidden)
- Dynamic page title (shows score + filename)
- Keyboard shortcut tooltips on buttons
- Upload progress: XHR with progress events (0-30% upload, 30-100% checking)

## v1.4 (2026-05-28)
- Upload progress bar (XHR progress events)
- Wording fixes: removed "伪造", "忽略大小写和标点" from suggestions
- "整理 Bib" button color changed from purple to slate
- Progress bar gradient: blue→cyan instead of blue→purple

## v1.3 (2026-05-28)
- "📥 获取官方 Bib" button on reference issues
- Fetch from DBLP/ACL Anthology/Crossref BibTeX API
- Copy to clipboard or auto-replace in editor

## v1.2 (2026-05-28)
- Visual progress bar for upload/checking (percentage + gate name)
- Overview gate cards clickable (enter workspace)
- F8 keyboard shortcut for next issue
- GATE_NAMES_ORDER updated to include writing_quality

## v1.1 (2026-05-28)
- Filler sentence detection ("it is important to note that" etc, >=5 = warning)
- Bib deduplication (same key or same title removed)
- Author name in body text detection (anonymization check)
- En-dash overuse detection (>20 = warning)
- LaTeX command typo detection (\bgein, \setcion etc = error)
- Double space detection (>10 lines = info)

## v1.0 (2026-05-28)
- GPT fake author pattern detection (all authors have top-20 common surnames)
- En-dash detection
- LaTeX command typo check
- Double space check
- Header stats badge (pass/total in workspace toolbar)

## v0.9 (2026-05-28)
- Multi-file tabs in editor (open/close/switch)
- Toast notification system (replaces all alert() calls)
- OpenAlex API as 4th verification source
- Abstract vs Conclusion duplication check
- "et al" formatting check (should have period)
- Overview page gate_description display

## v0.8 (2026-05-28)
- Gate 6: Writing Quality (AI traces, anonymization, typo, paragraph duplication)
- BibTeX cleaning tool (format + sort + separate unused)
- P-value suspicion detection (>=3 borderline values near 0.05)
- LaTeX autocomplete (triggers on backslash, 40+ commands)

## v0.7 (2026-05-28)
- Title search verification for no-DOI papers (Crossref + Semantic Scholar + OpenAlex)
- Benford's Law check (first-digit distribution, chi-squared test)
- Duplicate image detection (MD5 hash comparison)

## v0.6 (2026-05-28)
- "← 返回首页" and "🗑 删除此项目" buttons on overview
- History list items have 🗑 delete button
- Issue cards use emoji (❌/⚠️/✅) instead of ✗/⚠/✓
- "↓" floating button for next issue navigation
- Issue cards show "点击跳转到对应位置" tooltip

## v0.5 (2026-05-27)
- CodeMirror search addon (Ctrl+F, Ctrl+G)
- \bibliography{} file existence check
- Export report formatting overhaul (Unicode borders, professional layout)
- Ctrl+Shift+R keyboard shortcut for recheck

## v0.4 (2026-05-27)
- Retraction detection (Crossref update-to/relation fields)
- Duplicate \label detection
- Orphan \ref detection (refs to non-existent labels)
- Year consistency check (bib year vs database year)
- DOI format pre-validation (regex before API call)
- Self-citation ratio detection (>30% = warning)
- Check progress animation (button shows gate name as each completes)
- Bib entry line number tracking (source_file + source_line)

## v0.3 (2026-05-27)
- Semantic Scholar API as 3rd verification source
- Mobile responsive design (phone/tablet/desktop breakpoints)
- Appendix figure/table exemption (no \ref required)

## v0.2 (2026-05-27)
- JSON file persistence (data/jobs/*.json, survives server restart)
- History panel on upload page (resume previous jobs)
- GET /api/history + DELETE /api/job/{id} endpoints
- Startup cleanup of expired jobs (7-day retention)
- UI redesign: Overleaf-style dark file panel, fixed right panel
- Upload page branding (IntegrityGuard + feature list)
- DOI links in issue suggestions

## v0.1 (2026-05-27)
- Initial 5-gate system (structure, citations, references, figures, data)
- CodeMirror 5 LaTeX editor with syntax highlighting
- Inline error marking (gutter + text highlight)
- File CRUD API for editor
- Recheck endpoint
- Human-in-the-loop dismiss with reason
- Export report for supervisor
- Drag & drop upload
- Comment stripping in .tex parsing
- Trusted URL patterns (arxiv, neurips, openreview etc)
- Official bib URL links (ACL/DBLP/ACM/IEEE)
