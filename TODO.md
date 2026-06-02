# ScholarLint · 投稿通 - 产品开发 TODO

> 目标：打造一款让人眼前一亮的学术论文提交前质检 SaaS 产品
> 核心原则：宁可错杀不能放过（严格检查）、false positive 可接受、rule-based + LLM-based 结合

---

## 🔴 P0 — 核心功能完善（必须优先）

### 检查引擎强化
- [ ] **扩展引文数据库源**
  - [x] 添加 Semantic Scholar API 作为第三验证源（覆盖 CS 领域最全）
  - [x] 添加 OpenAlex API（免费、覆盖广、速度快）
  - [ ] 添加 Google Scholar 爬虫备份（通过 SerpAPI 或 scholarly）
  - [x] 对于无 DOI 论文，尝试 title search 在 Crossref/Semantic Scholar 中匹配
- [ ] **强化引文检查规则**
  - [x] 检查年份一致性（bib 中 year 与数据库 year 差 >1 年 → warning）
  - [x] 检查 DOI 格式合法性（正则预筛，减少无效 API 调用）
  - [x] 检测 GPT 生成的假作者模式（所有作者姓氏都在 top-20 常见姓列表）
  - [x] 检查引文是否被 retracted（通过 Crossref metadata）
  - [x] 检查自引比例（自引 > 30% → warning）
- [x] **数据完整性检查强化**
  - [x] 检测 Benford's Law 偏离（实验数据首位数字分布）
  - [x] 检测过于整齐的 p-value（如 p=0.049, p=0.048...≥3个 → p-hacking 警告）
  - [x] 检测结果数值与文字描述不一致（正文 achieve 0.86 vs 表格 0.85）
  - [x] 检测 copy-paste 的图片（MD5 hash 比对图片文件）
- [ ] **文件结构检查强化**
  - [x] 检查 \bibliography{} 指向的 .bib 文件是否存在
  - [x] 检查重复的 \label{} 定义
  - [x] 检查孤立的 \ref{} （引用了不存在的 label）
  - [x] 检查 appendix 中的 figure/table 不要求正文引用（修复当前误报）
- [x] **新增 Gate 6: 文本质量检查（已实现为 writing_quality gate）**
  - [ ] 检测段落级别的 AI 生成痕迹（perplexity 异常低 — 需要 LLM API）
  - [x] 检测 abstract 与 conclusion 过度重复
  - [x] 检测"万金油句子"（无实质内容的 filler text，>=5处 → warning）
  - [x] 检测格式不规范（"et al" 格式检查已加入 gate_writing）

### BibTeX 清理工具（核心特色功能）
- [x] **Bib Tidy 功能**
  - [x] 缩进整理（统一 2-space 缩进）
  - [x] 去除 abstract、keywords、file 等无用字段
  - [x] 字段名统一小写（Title → title）
  - [x] 去除重复条目
- [x] **按引用顺序排序 bib**（我们的特色：根据 .tex 中 \cite 出现顺序重排 .bib）
- [x] **分离未引用条目**（自动把 tex 中没 \cite 的条目移到 unused.bib）
- [x] **一键清理按钮**（在编辑器工具栏，点击后自动应用以上所有清理）

### 写作质量检查（Rule-based）
- [x] **AI 痕迹检测**
  - [x] em-dash (—) 过多检测（>8个 → warning）
  - [x] "Additionally", "Furthermore" 等 AI 常用连接词频率
  - [x] 检测遗留的 prompt 痕迹（如 "As an AI", "I cannot" 等）
  - [x] en-dash 滥用检测（>20次 → warning）
- [x] **段落重复检测**（两个自然段相似度 > 80% → warning）
- [x] **匿名化检查（Double-Blind）**
  - [x] 检查 \author{} 是否为空或占位符
  - [x] 检查自引暴露身份（"our previous work" 等）
  - [x] 检查正文中是否出现作者真名
  - [x] 检查 PDF metadata / comment 是否泄露作者信息（\hypersetup pdfauthor）
- [x] **Typo 检测**（40+ 常见学术拼写错误词典）
- [x] **Abstract vs Conclusion 重复检测**（>60% 相似 → warning）
- [x] **"et al" 格式检查**（应为 "et al." 带句点）

### Parser / Gate 准确性
- [x] cite parser 支持常见 natbib/biblatex 命令与 optional args
- [x] ref parser 支持 cleveref/autoref/subref/vref/range 基础命令
- [x] cite/ref parser 继续补充 `smartcite/supercite/citeyearpar/citeposs` 与 `pageref/nameref/namecref/cpageref`
- [x] parser/gate 测试覆盖无扩展名 `\includegraphics`、注释忽略与 `\graphicspath` 后缀解析

### 编辑器功能
- [x] **鼠标滚动修复验证**（CodeMirror position:absolute + overflow-y:auto）
- [x] **搜索替换功能**（Ctrl+F / Ctrl+G，通过 CodeMirror search addon）
- [x] **撤销重做**（CodeMirror 自带，已确认工作）
- [x] **多文件 tab**（点击文件打开新 tab，可关闭）
- [x] **LaTeX 语法补全**（输入 \ 后自动弹出常用命令列表）
- [x] **前端本地草稿与保存重试**
  - [x] 按文件维护 dirty / saving / error / pendingContent 状态
  - [x] 编辑时按 job + path 写入 localStorage 草稿，保存失败保留未同步内容
  - [x] Tab 显示未保存/保存失败指示，并提供当前文件“重试保存”入口
- [x] **编辑修改历史与回退**
  - [x] 每次保存记录历史（时间/文件/行数增减/前后内容），加密存储并限制最多 100 条
  - [x] 三个 API：列出时间线、查看 diff、回退到改动前（回退也记入历史）
  - [x] 工具栏「📜 修改历史」时间线弹窗 + 行级 diff + 一键回退；权限隔离（share token 只读不可回退）

---

## 🟡 P1 — 产品功能（第二优先）

### 用户系统
- [x] 用户注册/登录（邮箱 + 密码）
- [ ] OAuth 登录（GitHub/Google）
- [x] 用户 dashboard（我的论文列表、历史记录、统计）
- [x] 多论文管理（历史记录列表，每篇独立 job，可切换/删除）
- [ ] 团队/导师模式（导师可查看学生的所有检查记录）
- [x] 分享链接（?job=xxx URL，复制给导师即可查看）

### Copilot 自动修复（LLM-based）
- [x] "一键修复" 按钮：LLM 分析问题 → 弹窗展示建议代码 → 用户复制应用
- [x] 引用修复：自动从 ACL/DBLP 拉取正确 bib 条目替换（📥 按钮一键替换）
- [x] 格式修复：自动补全缺失的 \label（一键插入按钮）
- [x] 语言润色建议（超长句子检测、被动语态过多提醒）

### 订阅 & 付费
- [x] Free tier: 注册赠送 3 次检查，基础规则
- [x] Free tier 月度重置：每月刷新 3 次免费检查额度
- [ ] Pro tier: 无限检查 + LLM 深度分析 + Copilot 修复 + 优先 API
- [x] Pro/Team tier 权益：完整质检不消耗免费检查次数，前端上传不因 0 次余额误拦截
- [x] 付费套餐自动升级 tier：购买专业包升 Pro，购买实验室包升 Team
- [x] Team tier 导师 dashboard：展示最近检查平均分、通过率、待关注论文和低分列表
- [x] Pro/Team API Token 基础：付费用户可生成/撤销个人 API Token，服务端仅保存哈希
- [ ] Team tier: 导师 dashboard + 批量检查 + API 接入
- [ ] Stripe/支付宝 集成

### 报告增强
- [x] PDF 导出（打开打印窗口，浏览器另存为 PDF）
- [x] 检查证书（通过后生成 Certificate，可打印为 PDF）
- [x] 时间线视图（多次检查的分数变化趋势）
- [x] Markdown 导出报告后端品牌 header/footer（报告 ID、报告类型、官网、免责声明）
- [x] 对比视图（概览页展示前后两次检查分数、错误、警告和 gate 级 diff）

---

## 🟢 P2 — UI/UX 打磨

### 响应式设计
- [x] 手机端适配（upload 页单列、workspace 变垂直堆叠）
- [x] iPad/平板适配（双栏布局收窄）
- [x] 大屏居中问题修复
- [x] 深色模式支持（编辑器 material-darker 主题 + 🌙 toggle）

### 交互优化
- [x] 上传进度条（XHR progress event，0-30% 上传，30-100% 检查）
- [x] 检查进度动画（进度条 + 按钮文字实时更新 gate 名称）
- [x] 键盘快捷键（Ctrl+S/Ctrl+Shift+R/F8）
- [x] 右键菜单（跳转问题/重新质检/保存/整理Bib/导出报告）
- [x] Toast 通知（保存成功、检查完成等非阻塞提示）
- [x] Toast 去重与可见数量上限，避免网络/AI 错误刷屏
- [x] 空状态设计（无问题时显示 ✅ 提示）

### 视觉设计
- [x] 统一设计系统（CSS variables: colors, radius, shadows, font-mono）
- [x] 动画 transitions（fadeIn 页面切换 + slideUp issue 卡片）
- [x] 品牌 logo 静态资产接入（navbar 与上传页 hero 复用 `app/static/brand/logo.png`）
- [x] 对外报告、证书页脚、报告页标题与 HTTP User-Agent 统一为 ScholarLint · 投稿通 品牌命名
- [x] Loading skeleton（加载历史记录与恢复报告时的骨架屏）
- [x] 错误状态设计（网络错误 toast 提示、graceful fallback）
- [x] AI loading card 显示后台处理耗时，长请求更可观察
- [x] 文件树支持按文件名/路径搜索，文件多时可快速定位
- [x] Issue 面板长证据/建议默认折叠，避免撑爆侧栏，并支持 evidence 搜索

---

## 🔵 P3 — 技术债务 & 架构

### 代码重构
- [ ] 前端拆分：index.html → Vue/React SPA（组件化、状态管理）
- [ ] CSS 提取：inline styles → CSS modules / Tailwind classes
- [ ] API 类型安全：前后端共享 TypeScript types
- [x] AI diagnosis route 迁入 `app/api/ai_routes.py`，保持 `/api/ai-diagnosis/{job_id}` 兼容
- [x] AI review/polish/abstract routes 迁入 `app/api/ai_routes.py`，继续保持外部路径兼容
- [x] AI fix/batch-fix routes 迁入 `app/api/ai_routes.py`，所有 `/api/ai-*` 路径集中到 AI router
- [x] 测试覆盖：7 个单元测试（citations, structure, writing, data gates）
- [x] Error handling：全局异常处理中间件（返回 JSON 错误）
- [x] AI router API mock 测试覆盖 reference authenticity 单条/批量修复 guardrail
- [x] AI diagnosis API mock 测试覆盖成功 JSON、LLM fallback、missing job 404 与 payload 脱敏
- [x] AI router 权限测试覆盖 share token 只读用户不能调用 AI 写操作，且在 LLM 前拦截
- [x] 上传 API 集成测试覆盖真实解压/gate 编排、失败报告持久化、Zip Slip 与危险文件清理
- [x] 最小 API 级 E2E 覆盖 upload/report/files/save/recheck，验证编辑后重新质检会刷新报告并清除图表交叉引用问题
- [x] 共享测试 fixture：新增 `tests/conftest.py` 统一路由状态清理（`clear_route_state`），5 个测试文件去重 setup/teardown，降低维护与交接成本
- [x] 全局脱敏加固：`secrets_manager.redact()` 扩展覆盖 JWT、Bearer、PEM 块、API token 前缀、内部 LLM key 前缀；`_SENSITIVE_NAMES` 加入 JWT_SECRET/ADMIN_KEY/ALIPAY_*；新增 `tests/test_redact.py` 8 项
- [x] Legacy job 生产收紧：`_owner_metadata_allows` 在 `app_env=prod/production` 时拒绝缺 owner metadata 的 job（403），本地兼容保留；新增 `tests/test_legacy_owner_strict.py` 4 项
- [x] API Token 接入鉴权：`get_current_user_optional` 识别 `Authorization: Bearer sl_api_…`，按 SHA-256 hash 查 `api_tokens` 表，命中返回 user 并写 `last_used_at`；新增 `tests/test_api_token_auth.py` 7 项
- [x] 匿名 `sl_session` cookie Secure 对齐：与登录 cookie 同款判定（prod/HTTPS/x-forwarded-proto=https 自动 Secure）；新增 `tests/test_session_cookie_secure.py` 6 项
- [x] 拆分 routes.py：抽出 `app/api/file_routes.py`（list/read/save 文件 + 下载 ZIP 4 个端点），URL 不变、行为不变；4 个测试 fixture 同步挂载新 router
- [x] 拆分 routes.py 第二刀：抽出 `app/api/tool_routes.py`（bib-clean / fetch-bib / reference-candidates / tidyup GET+POST / format-normalize 共 5 端点），URL 不变；引用候选 helper 不再借 routes 跳板；test_ai_integrity 改直接从 ai_guardrails 导入
- [x] 拆分 routes.py 第三刀：抽出 `app/api/checklist_routes.py`（venue-checklist 单端点），URL 不变；routes.py 同步移除已无用的 CHECKLISTS import
- [x] routes.py 模块级文档加固：完整 docstring 列出剩余端点清单/共享基础设施/三条不变量；权限/会话/缓存核心 helper 与关键端点（upload/status/report）加详细 docstring；状态变量 inline 注释指向 clear_route_state；零行为变化
- [x] 抽出 `app/services/permissions.py`（M4）：9 个无状态权限/会话 helper 迁出（share-token / Secure cookie / owner_metadata_allows / can_access_report），通过 dependency injection 与 routes.py 模块级 state 解耦；新增 `tests/test_permissions_service.py` 17 项单元测试（pytest 133→150）
- [x] 文件树渲染 O(1) per file：per-report 预建 `_fileIssueIndex`（basename → 错误/已驳回 计数），`renderFileItem` / `getFileStatus` 从 O(files × gates × issues) 降为 O(1) 查询，与 v5.3.86/v5.3.89 形成完整的卡顿修复链
- [x] **安全**：`/api/report` share-token 路径脱敏——share-readonly 用户不再能拿到 owner_id / owner_type / session_id / share_token / project_dir / dismissed_issues 学生理由；保留 gate 结果与得分供导师审稿；新增 `tests/test_share_report_redaction.py` 5 项
- [x] **运维**：腾讯云 Lighthouse 部署套件——`docs/DEPLOY_TENCENT.md`（实例选型/环境变量/Nginx+SSL/ICP/COS备份/上线自检/回滚） + `docker-compose.prod.yml` overlay（绝对数据卷+有界日志+restart=always） + `.env.example` 模板 + `scripts/check-no-secrets.mjs`（npm run scan:tracked 预推送自检）；`.gitignore` 已覆盖 .env / secrets.enc / .jwt_secret / .admin_key

### 部署 & 运维
- [x] Docker 化（Dockerfile + docker-compose.yml + requirements.txt）
- [ ] CI/CD（GitHub Actions: lint + test + deploy）
- [x] CI 安全测试闭环：GitHub Actions 跑 ruff、JS 检查、secret scan、禁用隧道策略扫描和 pytest
- [x] CI 检查扩展：前端 inline JS 语法检查抽成本地脚本，加入临时隧道 provider policy scan，并扩展 secret scan 覆盖 LLM、隧道平台、JWT、admin 与支付密钥模式
- [x] 前端纯 helper 抽到全局脚本，并用 Node 内置测试覆盖 inline handler 参数、HTML escape、AI fix 文本替换与批量分组逻辑
- [x] 本地运行、测试与发布文档补齐：新增 docs 索引、本地启动指南、按改动类型组织的测试指南，并让 release checklist 引用统一测试命令集
- [x] AI 交接文档补齐：新增 `HANDOVER.md`，记录当前状态、风险、验证命令与下一步优先级
- [x] 根目录 `README.md` 补齐：项目定位、能力概览、目录结构、请求流程、快速启动、健康检查、测试验证与文档索引，改善 GitHub onboarding
- [x] 工程文档基线补齐：新增 `docs/ARCHITECTURE.md`（架构/请求流/权限模型/AI guardrail/已知风险）、`docs/CONFIGURATION.md`（配置项与密钥来源）、`docs/API_OVERVIEW.md`（按 router 分组端点参考），内容逐项对照真实代码核实，便于交接工程师
- [x] 禁止事项文档补齐：新增 `docs/DO_NOT_DO.md`，覆盖研究真实性、AI 修复验证、敏感文件/密钥提交边界、无关文件混入与未加固 dev server 公网暴露禁令
- [x] 安全部署文档补齐：新增 `docs/DEPLOY_SAFE.md`，覆盖 Docker、反向代理、HTTPS、生产开关、密钥注入、上传 ZIP 安全、健康检查、备份与公网暴露检查
- [x] 日志系统（structured logging with timestamp, level, module）
- [x] 监控（`/metrics` 暴露 uptime、API 延迟、错误率与按接口聚合统计）
- [x] Rate limiting（IP 级别，每小时 10 次上传）
- [x] 日志系统（structured logging 替换 print）
- [x] 文件安全扫描（上传的 zip 删除 .exe/.sh 等危险文件 + 100MB 限制）

### 数据库迁移
- [ ] 从 JSON 文件迁移到 PostgreSQL/SQLite
- [ ] 用户表、Job 表、Issue 表关系设计
- [x] 数据备份策略（`scripts/backup_data.py` + `docs/BACKUP.md`，默认备份 data，可选 uploads）
- [x] 大图项目质检性能优化：StructureGate 单次遍历 + 按大小分组算 MD5 + 流式 hash/尺寸读取（内存 12MB→2MB）；前端 issue 列表 dismissed Map 化（O(m×n)→O(1)）
- [x] 前端 dismissed 判定统一为共享 `isDismissed()`（按 report 缓存 Set）：文件树徽章/文件状态/编辑器标记等 6 处由全数组扫描改为 O(1) 查询

---

## 📋 版本记录

| 版本 | 日期 | 备份文件 | 改动 |
|------|------|---------|------|
| v0.1 | 2026-05-27 | (初始版本) | 基础 5-gate 系统 + 编辑器 + 检查 |
| v0.2 | 2026-05-27 | v0.2_...persistence-and-ui-overhaul.zip | 持久化存储、UI 重设计、上传页品牌介绍、DOI 链接 |
| v0.3 | 2026-05-27 | v0.3_...semantic-scholar-mobile-appendix-fix.zip | Semantic Scholar API、手机适配、appendix 图表豁免 |
| v0.4 | 2026-05-27 | v0.4_...retraction-detect-progress-anim-responsive.zip | Retraction 检测、重复label/孤立ref检查、年份一致性、DOI格式预检、自引比例、质检进度动画、bib行号定位 |
| v0.5 | 2026-05-27 | v0.5_...search-export-bibliography-check.zip | Ctrl+F搜索、\bibliography存在性检查、导出报告美化、Ctrl+Shift+R快捷键 |
| v0.6 | 2026-05-28 | v0.6_...nav-buttons-delete-emoji.zip | 返回首页/删除按钮、emoji替换✗、issue可点击跳转、↓浮动按钮 |
| v0.7 | 2026-05-28 | v0.7_...title-search-benford-dup-images.zip | 标题搜索验证无DOI引文、Benford定律、重复图片MD5检测 |
| v0.8 | 2026-05-28 | v0.8_...writing-gate-bib-clean-pvalue.zip | Gate6写作质量(AI痕迹/匿名化/typo/段落重复)、Bib清理工具、p-value检测、LaTeX补全 |
| v0.9 | 2026-05-28 | v0.9_...tabs-toast-openalex-abstract-etal.zip | 多文件tab、Toast通知、OpenAlex、abstract/conclusion重复、et al格式 |
| v1.0 | 2026-05-28 | v1.0_...full-feature-complete.zip | GPT假作者检测、en-dash检测、LaTeX命令typo、双空格检测、header stats badge |
| v1.1 | 2026-05-28 | v1.1_...filler-dedup-anonymize-names.zip | 万金油句子检测、bib去重、正文作者姓名检测 |
| v1.2 | 2026-05-28 | v1.2_...progress-bar-cards-clickable-f8.zip | 进度条可视化、overview卡片可点击、F8快捷键 |
| v1.3 | 2026-05-28 | v1.3_...fetch-official-bib-filler-detect.zip | 获取官方Bib按钮 |
| v1.4 | 2026-05-28 | v1.4_...upload-progress-wording-fixes.zip | XHR上传进度、文案优化 |
| v1.5 | 2026-05-28 | v1.5_...auto-replace-bib-notifications-ux.zip | 一键替换bib、浏览器通知、page title |
| v1.6 | 2026-05-28 | v1.6_...stats-summary-page-title.zip | 统计摘要、页面标题动态更新 |
| v1.7 | 2026-05-28 | v1.7_...wordcount-ref-detail-stats.zip | 词数统计、引文验证详情展开 |
| v1.8 | 2026-05-28 | v1.8_...auto-label-wordcount-ref-details.zip | 自动添加label按钮、词数统计、引文详情 |
| v1.9 | 2026-05-28 | v1.9_...dark-theme-auto-label-fix.zip | 深色主题编辑器、自动label修复 |
| v2.0 | 2026-05-28 | v2.0_...context-menu-transitions-ctrlS.zip | 右键菜单、动画过渡、Ctrl+S保存 |
| v2.1 | 2026-05-28 | v2.1_...error-handling-top-issues-linecount.zip | 全局异常处理、首要问题展示、行数统计 |
| v2.2 | 2026-05-28 | v2.2_...bib-compare-modal-flash-fix-matching.zip | Bib对比弹窗、跳转闪烁效果、标题匹配优化 |
| v2.3 | 2026-05-28 | v2.3_...white-theme-modular-showcase.zip | 白色首页主题、模块化功能展示区 |
| v2.4 | 2026-05-28 | v2.4_...css-vars-lang-polish-animations.zip | CSS变量系统、语言润色、动画优化 |
| v2.5 | 2026-05-28 | v2.5_...text-table-consistency-error-handler-polish.zip | 文本-表格一致性检测、错误处理、UI打磨 |
| v2.6 | 2026-05-28 | v2.6_...share-link-pdf-metadata-changelog.zip | 分享链接、PDF metadata检查 |
| v2.7 | 2026-05-28 | v2.7_...ai-fix-share-link-pdf-metadata.zip | AI修复建议、分享链接、PDF metadata |
| v2.8 | 2026-05-28 | v2.8_...ai-fix-badges-favicon-share.zip | AI修复完善、状态徽章、favicon |
| v2.9 | 2026-05-28 | v2.9_...tests-badges-favicon-final.zip | 单元测试、徽章系统、favicon最终版 |
| v3.0 | 2026-05-28 | v3.0_...docker-tests-production-ready.zip | Docker化、测试覆盖、生产环境就绪 |
| v3.1 | 2026-05-28 | v3.1_...ui-polish-bib-format-scroll-fix.zip | UI打磨、Bib格式化、滚动修复 |
| v3.2 | 2026-05-28 | v3.2_...venue-quality-ethics-check.zip | 引用质量分析（venue分布）、学术伦理检查 |
| v3.3 | 2026-05-28 | v3.3_...8-modules-venue-ethics.zip | 8模块展示区、venue质量完善 |
| v3.4 | 2026-05-28 | v3.4_...pdf-export-ratelimit-logging-cert.zip | 导出报告、限流、日志系统、检查证书 |
| v3.5 | 2026-05-28 | v3.5_...tidyup-tool-dragfix-exportfix.zip | 整理结构工具、拖拽修复、导出修复 |
| v3.6 | 2026-05-28 | v3.6_...filter-trend-stats-shortcuts-markdown.zip | 问题过滤器、分数趋势图、编辑器统计、快捷键帮助、Markdown导出 |
| v3.7 | 2026-05-28 | v3.7_...search-filter-skeleton-preview.zip | 问题搜索、骨架屏加载、Overview问题预览、script标签修复 |
| v3.8 | 2026-05-28 | v3.8_...collapsible-copy-download-tooltip.zip | 折叠分组、复制问题列表、下载文件、gutter tooltip |
| v3.9 | 2026-05-28 | v3.9_...analysis-checklist-citation-years.zip | 论文分析面板（章节字数+引文年份图）、投稿前清单 |
| v4.0 | 2026-05-28 | v4.0_...citation-freshness-gate.zip | 引文新鲜度检测规则（中位年份/近3年占比/陈旧论文警告） |
| v4.1 | 2026-05-28 | v4.1_...user-system-credits-sqlite.zip | 用户系统(注册/登录/JWT)、积分系统、SQLite数据库、交易记录 |
| v4.2 | 2026-05-28 | v4.2_...auth-ui-navbar-recharge-modal.zip | 前端登录注册弹窗、Navbar用户栏、充值套餐弹窗、积分显示 |
| v4.3 | 2026-05-28 | v4.3_...credits-integration-402-handling.zip | 积分扣减集成到upload/recheck、402余额不足弹窗、积分刷新 |
| v4.4 | 2026-05-28 | v4.4_...payment-sandbox-recharge-flow.zip | 支付系统(sandbox模式即时到账)、充值API、订单轮询、管理员充值 |
| v4.5 | 2026-05-28 | v4.5_...pricing-revamp-value-based.zip | 定价重设计(¥19.9/次)、注册送2次、按次计费 |
| v4.6 | 2026-05-28 | v4.6_...page-limit-limitations-format-detect.zip | 页数超限检测、会议格式识别(17种)、Limitations强制检查、bib缺字段检查 |

---

## 🚀 P0 — AI 功能增强（商业化核心卖点）

> 参考论文: [Multimodal Peer Review Simulation (WWW 2025 Demo)](https://arxiv.org/abs/2511.10902)
> 核心优势: 内部 LiteLLM 无限额度，AI 功能成本 ≈ ¥0，但用户感知价值极高

### 🎯 多模态审稿模拟（核心特色，来自 WWW Demo 论文）
- [ ] **RAG-based Reviewer Simulation**
  - [ ] 爬取 OpenReview 数据构建 review 知识库（按 venue/topic 分类）
  - [ ] 用户上传论文后，检索相似论文的真实 review 作为 few-shot context
  - [ ] 多模态 LLM 分析正文 + 图表（不只是文字，还看图是否清晰、表格是否规范）
  - [ ] 输出结构化 review: Strengths / Weaknesses / Questions / Score
- [ ] **Action:Objective To-Do 生成**
  - [ ] 将审稿意见转化为可执行的修改建议（Action:Objective[#] 格式）
  - [ ] 每条建议可点击跳转到论文对应位置
  - [ ] 用户可勾选完成状态，追踪修改进度
- [ ] **多维度评分**
  - [x] Novelty / Soundness / Clarity / Significance 四维评分
  - [ ] 对比同 venue 论文的平均分（基于 OpenReview 数据）

### ✨ AI 写作助手（已有 API，需加前端入口）
- [x] AI 单条修复建议（`/api/ai-fix`）
- [x] AI 审稿人模拟（`/api/ai-review` — 简版，已实现后端）
- [x] AI 段落润色（`/api/ai-polish` — 3 种模式：学术/精简/正式）
- [x] AI Abstract 优化（`/api/ai-abstract`）
- [x] **前端集成这些 API**
  - [x] 工具栏添加 "🤖 AI 助手" 下拉菜单
  - [x] 选中文本右键 → "AI 润色" / "AI 精简"
  - [x] Overview 页面添加 "模拟审稿" 按钮
  - [x] Abstract 检测到问题时显示 "AI 优化" 按钮
- [x] **AI 一键修复全部**
  - [x] 收集所有可自动修复的 issue → 批量调用 LLM → 生成 diff → 用户一键应用
  - [x] 后端返回 dry-run 预估（可修复条数、生成条数、跳过原因、gate 分组）
  - [x] 按 gate 分类展示批量建议（结构/写作/图表），支持分组应用
  - [x] 批量应用前提供 dry-run 预估（可替换条数、无法定位条数、风险等级）
- [x] **AI 论文诊断报告**
  - [x] 后端诊断接口（`/api/ai-diagnosis`）基于 gate 摘要生成结构化诊断
  - [x] 综合所有 gate 结果 + LLM 分析 → 生成一页诊断报告
  - [x] 包含：核心问题、修改优先级排序、预估修改时间
  - [x] 增加“先改哪三处”极速版本（30 秒可读）
  - [x] 修复诊断报告弹窗排版错位：优先级列表 flex 对齐、整行展示先改哪三处、2×2 等宽网格、统一表头与项目符号

### ✅ AI 可信输出强化
- [x] 审稿模拟明确标注“模拟意见”，并增加 Action Items
- [x] Abstract 优化加入 claim consistency guard，禁止夸大未被正文支持的 claim
- [x] Checklist 输出增加 evidence / missing_type / rewrite_suggestion
- [x] Checklist 结果支持复制 Markdown

### 📊 智能分析（低成本高价值）
- [x] 章节字数分布
- [x] 引文年份分布 + 新鲜度
- [ ] **引文网络可视化**（引用了谁、被谁引用 — 基于 S2 API）
- [x] **写作风格分析**（词汇多样性、句式复杂度、长句比例和高频重复词）
- [ ] **图表质量评估**（分辨率检查与标题检查已覆盖；字体大小是否可读待做）

### 🔧 格式自动修复（零 LLM 成本）
- [x] **一键格式规范化**（工作台 toolbar 入口 + 当前文件/全项目后端 API）
  - [x] 统一引用格式（保守统一裸 `\cite` → `\citep`，不改 `\citet` 语义引用）
  - [x] 统一数字格式（Table 1 vs Table~1 vs table 1）
  - [x] 统一缩写（Fig. vs Figure）
  - [x] 去除多余空行和空格 / 修复基础排版空白
- [ ] **Bib 自动补全**
  - [ ] 缺少 DOI 的条目自动从 Crossref 补全
  - [ ] 缺少 URL 的条目自动补全 Semantic Scholar 链接
- [x] **图片优化建议**
  - [x] 检测低分辨率/低像素图片（短边过小）
  - [x] 检测过大的 PDF/图片文件（可压缩）
  - [x] 建议矢量图替代位图

---

## 当前状态

- 服务运行在 http://localhost:8001（8000 被占用）
- 数据库: `data/integrity.db`（SQLite）
- 备份目录：`C:\Users\mengzehong\Desktop\integrity-assurance-backups\`
- 每次重大改动前备份，格式：`v{版本}_{日期}_{描述}.zip`
- 当前版本: v4.6（50+ 检测规则 + 用户系统 + 积分 + 支付）
