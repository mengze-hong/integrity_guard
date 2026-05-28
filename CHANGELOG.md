# IntegrityGuard Changelog

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
