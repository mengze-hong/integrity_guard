# ScholarLint · 投稿通 Changelog

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
