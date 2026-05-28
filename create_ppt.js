/**
 * IntegrityGuard Pitch Deck - Tencent Style
 * Color palette: Deep blue (#1A237E) + Tencent Blue (#0052D9) + Light accents
 */

const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
pres.author = "IntegrityGuard Team";
pres.title = "IntegrityGuard - Academic Paper Integrity Assurance";

// === Color Palette (Tencent-inspired) ===
const C = {
  primary: "0052D9",      // Tencent Blue
  dark: "0D1B3E",         // Deep navy
  darkBg: "0A1628",       // Slide background dark
  accent: "00C4B3",       // Teal accent
  accentGold: "F5A623",   // Gold accent
  white: "FFFFFF",
  lightGray: "F7F8FA",
  textGray: "8B95A5",
  textDark: "1D2129",
  cardBg: "FFFFFF",
  gradientStart: "0D1B3E",
  gradientEnd: "1A3A6B",
};

// === Helper: shadow factory ===
const makeShadow = () => ({
  type: "outer", color: "000000", blur: 8, offset: 3, angle: 135, opacity: 0.12
});

// === Screenshot paths ===
const SCREENSHOTS = path.join(__dirname, "screenshots_new");

// ============================================================
// SLIDE 1: Title Slide
// ============================================================
let slide1 = pres.addSlide();
slide1.background = { color: C.darkBg };

// Gradient overlay shape
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 0, w: 10, h: 5.625,
  fill: { color: C.dark, transparency: 30 }
});

// Decorative accent line
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 0.8, y: 2.0, w: 0.06, h: 1.6,
  fill: { color: C.accent }
});

// Title
slide1.addText("IntegrityGuard", {
  x: 1.1, y: 1.9, w: 7, h: 0.8,
  fontSize: 44, fontFace: "Arial Black", color: C.white, bold: true,
  margin: 0
});

// Subtitle
slide1.addText("学术论文提交前完整性保障系统", {
  x: 1.1, y: 2.7, w: 7, h: 0.5,
  fontSize: 20, fontFace: "Calibri", color: C.accent,
  margin: 0
});

// Tagline
slide1.addText("自动检测引用造假 · 数据异常 · 格式缺陷 · 写作问题\n避免 Desk Reject，保护学术声誉", {
  x: 1.1, y: 3.4, w: 6, h: 0.8,
  fontSize: 14, fontFace: "Calibri", color: C.textGray, lineSpacingMultiple: 1.5,
  margin: 0
});

// Version badge
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 1.1, y: 4.5, w: 1.2, h: 0.35,
  fill: { color: C.primary }, rectRadius: 0.02
});
slide1.addText("v4.0 Stable", {
  x: 1.1, y: 4.5, w: 1.2, h: 0.35,
  fontSize: 10, fontFace: "Calibri", color: C.white, align: "center", valign: "middle",
  margin: 0
});

// Right side: product screenshot (homepage hero)
slide1.addImage({
  path: path.join(SCREENSHOTS, "02_homepage_hero.png"),
  x: 5.5, y: 0.8, w: 4.2, h: 4.0,
  shadow: makeShadow()
});


// ============================================================
// SLIDE 2: Problem Statement
// ============================================================
let slide2 = pres.addSlide();
slide2.background = { color: C.white };

// Section label
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 0.5, y: 0.4, w: 1.4, h: 0.3,
  fill: { color: "E8F0FE" }
});
slide2.addText("PROBLEM", {
  x: 0.5, y: 0.4, w: 1.4, h: 0.3,
  fontSize: 9, fontFace: "Arial", color: C.primary, align: "center", valign: "middle",
  bold: true, charSpacing: 2, margin: 0
});

slide2.addText("学术论文提交的「最后一公里」问题", {
  x: 0.5, y: 1.0, w: 9, h: 0.6,
  fontSize: 28, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

slide2.addText("每年数百万篇论文因可避免的低级错误被 Desk Reject", {
  x: 0.5, y: 1.6, w: 9, h: 0.4,
  fontSize: 14, fontFace: "Calibri", color: C.textGray, margin: 0
});

// Problem cards - 2x2 grid
const problems = [
  { icon: "🔗", title: "引用造假/错误", desc: "DOI 无法解析、作者姓氏不匹配\n被撤回论文仍被引用", color: "FEE2E2" },
  { icon: "📊", title: "数据异常", desc: "p-value 过于整齐 (p-hacking)\n数值与表格不一致", color: "FEF3C7" },
  { icon: "📝", title: "格式缺陷", desc: "孤立引用、重复 label\n匿名化不完整 (double-blind)", color: "E0E7FF" },
  { icon: "🤖", title: "AI 痕迹", desc: "em-dash 过多、套话堆砌\n遗留 prompt 痕迹", color: "ECFDF5" },
];

problems.forEach((p, i) => {
  const col = i % 2;
  const row = Math.floor(i / 2);
  const x = 0.5 + col * 4.7;
  const y = 2.4 + row * 1.6;

  slide2.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 4.4, h: 1.4,
    fill: { color: p.color }, shadow: makeShadow()
  });
  slide2.addText(p.icon, {
    x: x + 0.2, y: y + 0.15, w: 0.5, h: 0.5,
    fontSize: 24, margin: 0
  });
  slide2.addText(p.title, {
    x: x + 0.7, y: y + 0.2, w: 3.4, h: 0.35,
    fontSize: 14, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
  });
  slide2.addText(p.desc, {
    x: x + 0.7, y: y + 0.55, w: 3.4, h: 0.7,
    fontSize: 11, fontFace: "Calibri", color: C.textGray, lineSpacingMultiple: 1.4, margin: 0
  });
});


// ============================================================
// SLIDE 3: Solution Overview
// ============================================================
let slide3 = pres.addSlide();
slide3.background = { color: C.darkBg };

slide3.addText("六道检查门，全方位守护", {
  x: 0.5, y: 0.5, w: 9, h: 0.6,
  fontSize: 28, fontFace: "Calibri", color: C.white, bold: true, margin: 0
});
slide3.addText("Rule-based + LLM-based 双引擎，宁可错杀不放过", {
  x: 0.5, y: 1.1, w: 9, h: 0.4,
  fontSize: 13, fontFace: "Calibri", color: C.textGray, margin: 0
});

// 6 gates in a horizontal flow
const gates = [
  { icon: "📁", name: "文件结构", desc: "完整性验证" },
  { icon: "🔗", name: "引用匹配", desc: "cite↔bib 一致" },
  { icon: "🔍", name: "引文真实", desc: "Crossref/S2 交叉验证" },
  { icon: "📊", name: "图表引用", desc: "float 正文引用" },
  { icon: "🧪", name: "数据完整", desc: "Benford/p-value" },
  { icon: "✍️", name: "写作质量", desc: "AI痕迹/匿名化" },
];

gates.forEach((g, i) => {
  const x = 0.4 + i * 1.6;
  const y = 1.9;

  // Circle background
  slide3.addShape(pres.shapes.OVAL, {
    x: x + 0.3, y, w: 0.9, h: 0.9,
    fill: { color: C.primary, transparency: 20 }
  });
  slide3.addText(g.icon, {
    x: x + 0.3, y, w: 0.9, h: 0.9,
    fontSize: 22, align: "center", valign: "middle", margin: 0
  });
  // Gate name
  slide3.addText(g.name, {
    x: x, y: y + 1.0, w: 1.5, h: 0.35,
    fontSize: 11, fontFace: "Calibri", color: C.white, align: "center", bold: true, margin: 0
  });
  // Gate desc
  slide3.addText(g.desc, {
    x: x, y: y + 1.3, w: 1.5, h: 0.3,
    fontSize: 9, fontFace: "Calibri", color: C.textGray, align: "center", margin: 0
  });

  // Connector line (except last)
  if (i < gates.length - 1) {
    slide3.addShape(pres.shapes.LINE, {
      x: x + 1.2, y: y + 0.45, w: 0.7, h: 0,
      line: { color: C.accent, width: 1.5, dashType: "dash" }
    });
  }
});

// Bottom: overview screenshot
slide3.addImage({
  path: path.join(SCREENSHOTS, "03_overview.png"),
  x: 0.8, y: 3.5, w: 8.4, h: 2.0,
  shadow: makeShadow()
});


// ============================================================
// SLIDE 4: Product Demo - Overview
// ============================================================
let slide4 = pres.addSlide();
slide4.background = { color: C.lightGray };

slide4.addText("一键质检，即时反馈", {
  x: 0.5, y: 0.4, w: 5, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

// Left: feature highlights
const features4 = [
  "上传 Overleaf 导出的 ZIP 即可开始",
  "6 道检查门自动运行，实时进度展示",
  "83/100 评分体系，通过/未通过一目了然",
  "错误/警告分级，优先修复关键问题",
  "分享链接给导师，协同审阅",
];
slide4.addText(features4.map(f => ({ text: f, options: { bullet: true, breakLine: true } })), {
  x: 0.5, y: 1.1, w: 4.5, h: 2.5,
  fontSize: 12, fontFace: "Calibri", color: C.textGray, lineSpacingMultiple: 1.8, margin: 0,
  paraSpaceAfter: 6
});

// Right: overview screenshot
slide4.addImage({
  path: path.join(SCREENSHOTS, "03_overview.png"),
  x: 5.2, y: 0.3, w: 4.6, h: 5.0,
  shadow: makeShadow()
});


// ============================================================
// SLIDE 5: Product Demo - Workspace
// ============================================================
let slide5 = pres.addSlide();
slide5.background = { color: C.lightGray };

slide5.addText("智能工作台：编辑 + 修复一体化", {
  x: 0.5, y: 0.3, w: 9, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

// Full-width workspace screenshot
slide5.addImage({
  path: path.join(SCREENSHOTS, "05_workspace.png"),
  x: 0.3, y: 1.0, w: 9.4, h: 4.4,
  shadow: makeShadow()
});

// Feature callouts at bottom
const wsFeatures = [
  { label: "LaTeX 编辑器", desc: "语法高亮 + 自动补全" },
  { label: "问题面板", desc: "按文件分组，一键跳转" },
  { label: "AI 修复", desc: "LLM 生成修复建议" },
  { label: "Bib 整理", desc: "格式化 + 排序 + 去重" },
];
wsFeatures.forEach((f, i) => {
  const x = 0.3 + i * 2.4;
  slide5.addShape(pres.shapes.RECTANGLE, {
    x, y: 5.05, w: 0.04, h: 0.45,
    fill: { color: C.accent }
  });
  slide5.addText(f.label, {
    x: x + 0.15, y: 5.05, w: 2.1, h: 0.22,
    fontSize: 10, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
  });
  slide5.addText(f.desc, {
    x: x + 0.15, y: 5.27, w: 2.1, h: 0.22,
    fontSize: 9, fontFace: "Calibri", color: C.textGray, margin: 0
  });
});


// ============================================================
// SLIDE 6: Key Features Deep Dive
// ============================================================
let slide6 = pres.addSlide();
slide6.background = { color: C.white };

slide6.addText("核心能力矩阵", {
  x: 0.5, y: 0.4, w: 9, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

// 3x2 feature grid
const coreFeatures = [
  { icon: "🔍", title: "引文真实性验证", desc: "Crossref + Semantic Scholar + OpenAlex\n三源交叉验证，检测假 DOI/假作者", color: C.primary },
  { icon: "📐", title: "Benford 定律检测", desc: "实验数据首位数字分布分析\n识别数据编造和 p-hacking", color: "7C3AED" },
  { icon: "🤖", title: "AI 痕迹检测", desc: "em-dash/en-dash 频率、套话密度\n遗留 prompt 痕迹扫描", color: "DC2626" },
  { icon: "📋", title: "BibTeX 智能整理", desc: "按引用顺序排序、去重、格式化\n分离未引用条目到 unused.bib", color: "059669" },
  { icon: "🔒", title: "匿名化检查", desc: "Double-blind 合规检测\n作者姓名/自引/metadata 泄露", color: "D97706" },
  { icon: "🛠️", title: "AI Copilot 修复", desc: "LLM 分析问题生成修复代码\n一键获取官方 Bib 替换", color: "0891B2" },
];

coreFeatures.forEach((f, i) => {
  const col = i % 3;
  const row = Math.floor(i / 3);
  const x = 0.5 + col * 3.1;
  const y = 1.2 + row * 2.2;

  // Card
  slide6.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 2.9, h: 2.0,
    fill: { color: C.cardBg },
    line: { color: "E5E7EB", width: 1 },
    shadow: makeShadow()
  });
  // Color accent top bar
  slide6.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 2.9, h: 0.05,
    fill: { color: f.color }
  });
  // Icon
  slide6.addText(f.icon, {
    x: x + 0.2, y: y + 0.2, w: 0.5, h: 0.5,
    fontSize: 22, margin: 0
  });
  // Title
  slide6.addText(f.title, {
    x: x + 0.2, y: y + 0.7, w: 2.5, h: 0.3,
    fontSize: 12, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
  });
  // Desc
  slide6.addText(f.desc, {
    x: x + 0.2, y: y + 1.0, w: 2.5, h: 0.8,
    fontSize: 10, fontFace: "Calibri", color: C.textGray, lineSpacingMultiple: 1.4, margin: 0
  });
});


// ============================================================
// SLIDE 7: Technical Architecture
// ============================================================
let slide7 = pres.addSlide();
slide7.background = { color: C.darkBg };

slide7.addText("技术架构", {
  x: 0.5, y: 0.4, w: 9, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.white, bold: true, margin: 0
});

// Architecture layers
const layers = [
  { label: "前端", items: "单页应用 · CodeMirror 编辑器 · 响应式设计 · 深色模式", y: 1.2, color: "3B82F6" },
  { label: "API 层", items: "FastAPI · RESTful · 异步处理 · Rate Limiting", y: 2.2, color: "8B5CF6" },
  { label: "检查引擎", items: "6-Gate Pipeline · Rule-based + LLM · 并行执行", y: 3.2, color: "10B981" },
  { label: "外部服务", items: "Crossref · Semantic Scholar · OpenAlex · LLM API", y: 4.2, color: "F59E0B" },
];

layers.forEach(l => {
  // Layer bar
  slide7.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: l.y, w: 9, h: 0.75,
    fill: { color: l.color, transparency: 80 },
    line: { color: l.color, width: 1 }
  });
  // Label
  slide7.addShape(pres.shapes.RECTANGLE, {
    x: 0.5, y: l.y, w: 1.5, h: 0.75,
    fill: { color: l.color }
  });
  slide7.addText(l.label, {
    x: 0.5, y: l.y, w: 1.5, h: 0.75,
    fontSize: 11, fontFace: "Calibri", color: C.white, align: "center", valign: "middle",
    bold: true, margin: 0
  });
  // Items
  slide7.addText(l.items, {
    x: 2.2, y: l.y, w: 7, h: 0.75,
    fontSize: 12, fontFace: "Calibri", color: C.white, valign: "middle", margin: 0
  });
});

// Tech stack badges
slide7.addText("Python 3.14 · FastAPI · Docker · Playwright · Node.js", {
  x: 0.5, y: 5.1, w: 9, h: 0.3,
  fontSize: 10, fontFace: "Calibri", color: C.textGray, align: "center", margin: 0
});


// ============================================================
// SLIDE 8: Metrics & Traction
// ============================================================
let slide8 = pres.addSlide();
slide8.background = { color: C.white };

slide8.addText("产品数据", {
  x: 0.5, y: 0.4, w: 9, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

// Big number stats
const stats = [
  { num: "200+", label: "论文已检查", color: C.primary },
  { num: "6", label: "检查维度", color: "7C3AED" },
  { num: "40+", label: "检测规则", color: "059669" },
  { num: "3", label: "外部验证源", color: "D97706" },
];

stats.forEach((s, i) => {
  const x = 0.5 + i * 2.4;
  slide8.addShape(pres.shapes.RECTANGLE, {
    x, y: 1.2, w: 2.2, h: 1.5,
    fill: { color: C.lightGray },
    shadow: makeShadow()
  });
  slide8.addText(s.num, {
    x, y: 1.3, w: 2.2, h: 0.8,
    fontSize: 36, fontFace: "Arial Black", color: s.color, align: "center", valign: "middle",
    bold: true, margin: 0
  });
  slide8.addText(s.label, {
    x, y: 2.1, w: 2.2, h: 0.4,
    fontSize: 11, fontFace: "Calibri", color: C.textGray, align: "center", margin: 0
  });
});

// Supported venues
slide8.addText("支持顶会格式", {
  x: 0.5, y: 3.2, w: 9, h: 0.4,
  fontSize: 14, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

const venues = ["ACL", "NeurIPS", "EMNLP", "ICLR", "CVPR", "AAAI", "ICML", "KDD"];
venues.forEach((v, i) => {
  const x = 0.5 + i * 1.15;
  slide8.addShape(pres.shapes.RECTANGLE, {
    x, y: 3.7, w: 1.0, h: 0.4,
    fill: { color: "E8F0FE" }
  });
  slide8.addText(v, {
    x, y: 3.7, w: 1.0, h: 0.4,
    fontSize: 10, fontFace: "Calibri", color: C.primary, align: "center", valign: "middle",
    bold: true, margin: 0
  });
});

// Feature completeness
slide8.addText("功能完成度", {
  x: 0.5, y: 4.4, w: 9, h: 0.4,
  fontSize: 14, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

const progress = [
  { label: "核心检查引擎", pct: 95 },
  { label: "编辑器 & 工作台", pct: 100 },
  { label: "AI Copilot 修复", pct: 85 },
  { label: "用户系统 & 付费", pct: 20 },
];

progress.forEach((p, i) => {
  const y = 4.85 + i * 0.35;
  slide8.addText(p.label, {
    x: 0.5, y, w: 2.0, h: 0.3,
    fontSize: 10, fontFace: "Calibri", color: C.textGray, margin: 0
  });
  // Background bar
  slide8.addShape(pres.shapes.RECTANGLE, {
    x: 2.6, y: y + 0.08, w: 6.0, h: 0.15,
    fill: { color: "E5E7EB" }
  });
  // Progress bar
  slide8.addShape(pres.shapes.RECTANGLE, {
    x: 2.6, y: y + 0.08, w: 6.0 * (p.pct / 100), h: 0.15,
    fill: { color: p.pct >= 80 ? "10B981" : p.pct >= 50 ? "F59E0B" : "EF4444" }
  });
  // Percentage
  slide8.addText(`${p.pct}%`, {
    x: 8.8, y, w: 0.7, h: 0.3,
    fontSize: 9, fontFace: "Calibri", color: C.textGray, align: "right", margin: 0
  });
});


// ============================================================
// SLIDE 9: Roadmap
// ============================================================
let slide9 = pres.addSlide();
slide9.background = { color: C.lightGray };

slide9.addText("产品路线图", {
  x: 0.5, y: 0.4, w: 9, h: 0.5,
  fontSize: 24, fontFace: "Calibri", color: C.textDark, bold: true, margin: 0
});

// Timeline
const roadmap = [
  { phase: "已完成", items: "6-Gate 检查引擎\nBib 智能整理\nAI Copilot 修复\nDocker 部署", color: "10B981" },
  { phase: "Q3 2026", items: "用户系统 & 登录\nStripe 付费集成\nCI/CD 自动化\n对比视图", color: C.primary },
  { phase: "Q4 2026", items: "团队/导师模式\n批量检查 API\nGoogle Scholar 集成\n数据库迁移", color: "8B5CF6" },
  { phase: "2027", items: "SaaS 公开发布\n多语言支持\n插件生态\n企业版", color: "F59E0B" },
];

roadmap.forEach((r, i) => {
  const x = 0.3 + i * 2.45;
  const y = 1.2;

  // Phase card
  slide9.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 2.3, h: 4.0,
    fill: { color: C.cardBg },
    shadow: makeShadow()
  });
  // Color top bar
  slide9.addShape(pres.shapes.RECTANGLE, {
    x, y, w: 2.3, h: 0.06,
    fill: { color: r.color }
  });
  // Phase label
  slide9.addShape(pres.shapes.RECTANGLE, {
    x: x + 0.2, y: y + 0.3, w: 1.2, h: 0.35,
    fill: { color: r.color, transparency: 85 }
  });
  slide9.addText(r.phase, {
    x: x + 0.2, y: y + 0.3, w: 1.2, h: 0.35,
    fontSize: 10, fontFace: "Calibri", color: r.color, align: "center", valign: "middle",
    bold: true, margin: 0
  });
  // Items
  slide9.addText(r.items, {
    x: x + 0.2, y: y + 0.9, w: 1.9, h: 2.8,
    fontSize: 11, fontFace: "Calibri", color: C.textGray, lineSpacingMultiple: 1.8, margin: 0
  });
});


// ============================================================
// SLIDE 10: Call to Action
// ============================================================
let slide10 = pres.addSlide();
slide10.background = { color: C.darkBg };

// Decorative accent
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 4.2, y: 1.5, w: 1.6, h: 0.05,
  fill: { color: C.accent }
});

slide10.addText("让每一篇论文\n都经得起审查", {
  x: 1, y: 1.8, w: 8, h: 1.4,
  fontSize: 36, fontFace: "Calibri", color: C.white, bold: true,
  align: "center", lineSpacingMultiple: 1.4, margin: 0
});

slide10.addText("IntegrityGuard — 学术诚信的最后一道防线", {
  x: 1, y: 3.3, w: 8, h: 0.5,
  fontSize: 16, fontFace: "Calibri", color: C.accent, align: "center", margin: 0
});

// CTA buttons
slide10.addShape(pres.shapes.RECTANGLE, {
  x: 3.2, y: 4.2, w: 1.8, h: 0.5,
  fill: { color: C.primary }
});
slide10.addText("立即体验 →", {
  x: 3.2, y: 4.2, w: 1.8, h: 0.5,
  fontSize: 12, fontFace: "Calibri", color: C.white, align: "center", valign: "middle",
  bold: true, margin: 0
});

slide10.addShape(pres.shapes.RECTANGLE, {
  x: 5.3, y: 4.2, w: 1.8, h: 0.5,
  fill: { color: C.darkBg },
  line: { color: C.textGray, width: 1 }
});
slide10.addText("联系我们", {
  x: 5.3, y: 4.2, w: 1.8, h: 0.5,
  fontSize: 12, fontFace: "Calibri", color: C.white, align: "center", valign: "middle",
  margin: 0
});

// Contact info
slide10.addText("🌐 localhost:8000  |  📧 integrity@example.com  |  💬 企业微信群", {
  x: 1, y: 5.0, w: 8, h: 0.3,
  fontSize: 10, fontFace: "Calibri", color: C.textGray, align: "center", margin: 0
});


// ============================================================
// Save
// ============================================================
const outputPath = path.join(__dirname, "IntegrityGuard_Pitch_Deck.pptx");
pres.writeFile({ fileName: outputPath })
  .then(() => {
    console.log(`\n✅ PPT saved to: ${outputPath}`);
    console.log("   10 slides, Tencent-style design");
  })
  .catch(err => {
    console.error("Error:", err);
  });
