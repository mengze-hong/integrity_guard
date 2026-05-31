# ScholarLint · 投稿通 Changelog

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
