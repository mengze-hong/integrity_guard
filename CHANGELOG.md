# ScholarLint · 投稿通 Changelog

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
