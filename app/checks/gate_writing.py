"""Gate 6: 写作质量检查（Rule-based）

检测内容：
1. AI 生成痕迹（em-dash 泛滥、AI 常用词、prompt 残留）
2. 段落重复（两段高度相似）
3. 匿名化检查（Double-Blind 投稿准备）
4. 常见 typo
"""

import re
from difflib import SequenceMatcher

from app.checks.base import BaseGate
from app.models import CheckResult, Issue, ParsedPaper, Severity


# AI signature words/phrases
_AI_MARKERS = [
    "as an ai", "as a language model", "i cannot", "i can't help",
    "here is a", "here's a", "certainly!", "absolutely!",
    "it's worth noting", "it is worth noting",
    "in conclusion,", "in summary,",  # these are ok alone, but flagged with others
]

_AI_CONNECTOR_WORDS = [
    "additionally", "furthermore", "moreover", "consequently",
    "nevertheless", "nonetheless", "subsequently", "henceforth",
    "delve", "delving", "utilize", "utilizing", "utilization",
    "facilitate", "facilitating", "comprehensive", "comprehensively",
    "leveraging", "leverage", "paradigm", "multifaceted",
]

# Filler sentences that add no substance (common in AI-generated or padded text)
_FILLER_PATTERNS = [
    r"it is important to note that",
    r"it should be noted that",
    r"it is worth mentioning that",
    r"it goes without saying that",
    r"needless to say",
    r"in today'?s rapidly (?:changing|evolving)",
    r"in recent years.{0,20}has (?:gained|attracted|received) (?:significant|considerable|increasing)",
    r"plays a (?:crucial|vital|important|significant|key) role",
    r"has become (?:increasingly|more and more) (?:important|popular|prevalent)",
    r"a growing body of (?:research|literature|evidence)",
    r"to the best of our knowledge",
    r"the rest of (?:this|the) paper is organized as follows",
]

# Common academic typos
_TYPO_DICT = {
    "acheive": "achieve", "acheived": "achieved", "acheiving": "achieving",
    "occurence": "occurrence", "occured": "occurred",
    "seperate": "separate", "seperately": "separately",
    "accomodate": "accommodate", "accomodation": "accommodation",
    "definately": "definitely", "definatly": "definitely",
    "enviroment": "environment", "enviromental": "environmental",
    "independant": "independent", "independantly": "independently",
    "occassion": "occasion", "occassionally": "occasionally",
    "recieve": "receive", "recieved": "received",
    "succesful": "successful", "succesfully": "successfully",
    "untill": "until", "withing": "within",
    "teh": "the", "taht": "that", "wiht": "with",
    "thier": "their", "alot": "a lot",
    "performace": "performance", "preformance": "performance",
    "experiement": "experiment", "experiements": "experiments",
    "evalution": "evaluation", "avaluation": "evaluation",
    "comparision": "comparison", "comparisions": "comparisons",
    "diffentent": "different", "differnet": "different",
    "algorthm": "algorithm", "algortihm": "algorithm",
    "implmentation": "implementation", "implemntation": "implementation",
}

# Anonymization patterns
_SELF_CITE_PATTERNS = [
    r"our (?:previous|prior|earlier|recent) (?:work|paper|study|research)",
    r"we (?:previously|earlier|recently) (?:proposed|presented|introduced|showed)",
    r"in our (?:previous|prior) (?:work|paper)",
    r"\[(?:anonymous|self-cite|our work)\]",
]


class WritingQualityGate(BaseGate):
    """Gate 6: 写作质量检查"""

    name = "writing_quality"
    description = "写作质量：检测 AI 痕迹、段落重复、匿名化问题、拼写错误"
    is_blocking = False  # Warning level

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []

        for tex_file in paper.tex_files:
            if not tex_file.is_main and not tex_file.raw_text.strip():
                continue
            text = tex_file.raw_text
            lines = text.split("\n")

            # === AI Trace Detection ===
            # 1. Em-dash count
            em_dash_count = text.count("—") + text.count("---")
            if em_dash_count > 8:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Em-dash (—) 使用过多: {em_dash_count} 次",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="GPT 生成的文本倾向于大量使用 em-dash。学术论文中通常较少使用。",
                    suggestion="考虑将部分 em-dash 替换为逗号、分号或括号。",
                ))

            # 1.5 En-dash misuse (using -- where - should be, or vice versa)
            en_dash_count = text.count("–") + text.count("--")
            if en_dash_count > 20:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"En-dash (–/--) 使用频繁: {en_dash_count} 次",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="大量 en-dash 可能表明格式不统一。学术论文中 en-dash 主要用于数字范围（如 pages 1--10）。",
                    suggestion="确认 en-dash 用途是否正确。数字范围用 --，破折号用 ---。",
                ))

            # 2. AI connector word frequency
            text_lower = text.lower()
            ai_word_count = 0
            found_ai_words = []
            for word in _AI_CONNECTOR_WORDS:
                count = text_lower.count(word)
                if count > 0:
                    ai_word_count += count
                    found_ai_words.append(f"{word}({count})")

            if ai_word_count > 15:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"AI 常用词频率偏高: {ai_word_count} 次",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence=f"高频词: {', '.join(found_ai_words[:8])}",
                    suggestion="这些词在 AI 生成文本中出现频率远高于人类写作。建议替换为更自然的表达。",
                ))

            # 3. Prompt leakage
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                for marker in _AI_MARKERS:
                    if marker in line_lower:
                        issues.append(Issue(
                            severity=Severity.ERROR,
                            message=f"疑似 AI prompt 残留: \"{marker}\"",
                            location=f"{tex_file.path.name}:{i}",
                            file=tex_file.path.name,
                            line=i,
                            evidence=line.strip()[:100],
                            suggestion="这段文字包含明显的 AI 生成痕迹，请删除或重写。",
                        ))
                        break  # One per line is enough

            # === Paragraph Duplication ===
            paragraphs = self._extract_paragraphs(text)
            for i in range(len(paragraphs)):
                for j in range(i+1, len(paragraphs)):
                    if len(paragraphs[i]["text"]) < 100 or len(paragraphs[j]["text"]) < 100:
                        continue
                    sim = SequenceMatcher(None, paragraphs[i]["text"], paragraphs[j]["text"]).ratio()
                    if sim > 0.80:
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            message=f"两个段落高度相似（{sim:.0%}）",
                            location=f"{tex_file.path.name}:{paragraphs[i]['line']}",
                            file=tex_file.path.name,
                            line=paragraphs[i]["line"],
                            evidence=f"段落1 (行{paragraphs[i]['line']}): {paragraphs[i]['text'][:60]}...\n段落2 (行{paragraphs[j]['line']}): {paragraphs[j]['text'][:60]}...",
                            suggestion="两段内容几乎相同，可能是 copy-paste 遗留。请检查是否需要删除或改写。",
                        ))

            # === Anonymization Check ===
            # Check for [final] mode in ACL/EMNLP templates (should be [review] for double-blind)
            final_match = re.search(r"\\usepackage\[final\]\{(acl|emnlp|naacl|eacl|coling)\}", text)
            if final_match:
                line_num = text[:final_match.start()].count("\n") + 1
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message="投稿模式为 [final]，double-blind 应使用 [review]",
                    location=f"{tex_file.path.name}:{line_num}",
                    file=tex_file.path.name,
                    line=line_num,
                    evidence=final_match.group(0),
                    suggestion=f"将 \\usepackage[final]{{{final_match.group(1)}}} 改为 \\usepackage[review]{{{final_match.group(1)}}} 以启用匿名模式。",
                ))

            # Check \author{} content (only warn if [final] mode detected)
            author_match = re.search(r"\\author\{(.+?)\}", text, re.DOTALL)
            author_content = ""
            if author_match:
                author_content = author_match.group(1).strip()

            # Check for PDF metadata leaking author info (\hypersetup, \pdfinfo)
            hypersetup = re.search(r"\\hypersetup\{(.*?)\}", text, re.DOTALL)
            if hypersetup:
                hs_content = hypersetup.group(1)
                if re.search(r"pdfauthor\s*=", hs_content, re.IGNORECASE):
                    line_num = text[:hypersetup.start()].count("\n") + 1
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        message="\\hypersetup 中包含 pdfauthor（PDF metadata 泄露作者）",
                        location=f"{tex_file.path.name}:{line_num}",
                        file=tex_file.path.name,
                        line=line_num,
                        evidence=hs_content.strip()[:80],
                        suggestion="Double-blind 投稿前请删除 \\hypersetup 中的 pdfauthor 字段。",
                    ))

            # Check for self-citation patterns
            for i, line in enumerate(lines, 1):
                for pat in _SELF_CITE_PATTERNS:
                    if re.search(pat, line, re.IGNORECASE):
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            message="可能泄露作者身份的自引表述",
                            location=f"{tex_file.path.name}:{i}",
                            file=tex_file.path.name,
                            line=i,
                            evidence=line.strip()[:100],
                            suggestion="Double-blind 投稿中应避免 'our previous work' 等暴露身份的表述。建议改为 'Prior work [X]'。",
                        ))
                        break

            # Check if author names appear in body text
            if tex_file.is_main and author_content:
                # Extract author names
                author_names_raw = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", author_content)
                author_names_raw = re.sub(r"[\\{}^_$]", "", author_names_raw)
                # Split by common delimiters
                name_parts = re.split(r"\band\b|,|\\\\\s*", author_names_raw)
                author_surnames = []
                for part in name_parts:
                    words = part.strip().split()
                    if words and len(words[-1]) > 2:
                        author_surnames.append(words[-1])

                # Search for surnames in body (after \begin{document})
                body_start = text.find("\\begin{document}")
                if body_start > 0 and author_surnames:
                    body_text = text[body_start:]
                    found_names = []
                    for surname in author_surnames:
                        # Skip very common words that happen to be names
                        if surname.lower() in {"and", "the", "for", "from", "with"}:
                            continue
                        if re.search(r"\b" + re.escape(surname) + r"\b", body_text):
                            # Check it's not inside a \cite or \author command
                            occurrences = [m for m in re.finditer(r"\b" + re.escape(surname) + r"\b", body_text)]
                            for occ in occurrences[:1]:
                                context = body_text[max(0,occ.start()-20):occ.end()+20]
                                if "\\cite" not in context and "\\author" not in context and "@" not in context:
                                    found_names.append(surname)
                                    break

                    if found_names:
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            message=f"正文中出现作者姓氏: {', '.join(found_names)}",
                            location=tex_file.path.name,
                            file=tex_file.path.name,
                            evidence=f"检测到的姓氏: {', '.join(found_names)}（可能暴露作者身份）",
                            suggestion="Double-blind 投稿中，正文不应出现作者自己的姓名。请检查是否为自引语境。",
                        ))

            # === Typo Detection ===
            words = re.findall(r"\b[a-zA-Z]{3,}\b", text)
            typo_found = {}
            for word in words:
                w_lower = word.lower()
                if w_lower in _TYPO_DICT and w_lower not in typo_found:
                    typo_found[w_lower] = _TYPO_DICT[w_lower]

            if typo_found:
                evidence = "\n".join(f"  {wrong} → {right}" for wrong, right in list(typo_found.items())[:8])
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"发现 {len(typo_found)} 个拼写错误",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence=evidence,
                    suggestion="请修正以上拼写错误。",
                ))

            # LaTeX command typos
            latex_typos = {
                "\\bgein": "\\begin", "\\ednl": "\\end", "\\setcion": "\\section",
                "\\subsecton": "\\subsection", "\\includegrahics": "\\includegraphics",
                "\\uspackage": "\\usepackage", "\\newcommnad": "\\newcommand",
                "\\renewcommnad": "\\renewcommand", "\\documnetclass": "\\documentclass",
                "\\bibliograpy": "\\bibliography", "\\refernce": "\\reference",
                "\\captoin": "\\caption", "\\tbale": "\\table", "\\fgiure": "\\figure",
            }
            found_latex_typos = []
            for wrong, right in latex_typos.items():
                if wrong in text:
                    found_latex_typos.append(f"{wrong} → {right}")

            if found_latex_typos:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"LaTeX 命令拼写错误: {len(found_latex_typos)} 处",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="\n".join(f"  {t}" for t in found_latex_typos),
                    suggestion="这些命令拼写错误会导致编译失败。请修正。",
                ))

            # Double spaces (cosmetic but sloppy)
            double_space_lines = [i for i, line in enumerate(lines, 1)
                                  if "  " in line and not line.strip().startswith("%")]
            if len(double_space_lines) > 10:
                issues.append(Issue(
                    severity=Severity.INFO,
                    message=f"发现 {len(double_space_lines)} 行含有多余双空格",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    suggestion="虽然不影响编译，但双空格不规范。可使用编辑器的正则替换清理。",
                ))

            # Filler sentence detection
            filler_count = 0
            filler_examples = []
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                for pat in _FILLER_PATTERNS:
                    if re.search(pat, line_lower):
                        filler_count += 1
                        if len(filler_examples) < 3:
                            filler_examples.append(f"L{i}: {line.strip()[:60]}")
                        break

            if filler_count >= 5:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"检测到 {filler_count} 处套话/万金油句子",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="\n".join(filler_examples),
                    suggestion="这些句子常见于 AI 生成或凑字数的文本，缺乏实质内容。建议删除或替换为具体论述。",
                ))

            # === Language Polish Suggestions ===
            # 1. Overly long sentences (>50 words)
            long_sentences = 0
            longest_line = 0
            longest_line_num = 0
            longest_line_words = 0
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("\\") or len(stripped) < 20:
                    continue
                word_count = len(stripped.split())
                if word_count > 50:
                    long_sentences += 1
                    if word_count > longest_line_words:
                        longest_line_words = word_count
                        longest_line_num = i
                        longest_line = stripped

            if long_sentences > 5:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"发现 {long_sentences} 个超长句子（>50 词），最长 {longest_line_words} 词在行 {longest_line_num}",
                    location=f"{tex_file.path.name}:{longest_line_num}",
                    file=tex_file.path.name,
                    line=longest_line_num,
                    evidence=f"最长句: {longest_line[:100]}...",
                    suggestion="超长句子影响可读性。建议拆分为多个短句，每句 20-30 词为宜。点击可跳转到最长的那句。",
                ))

            # 2. Passive voice overuse (simple heuristic)
            passive_patterns = re.findall(
                r"\b(?:is|are|was|were|been|being)\s+\w+ed\b",
                text, re.IGNORECASE
            )
            if len(passive_patterns) > 20:
                issues.append(Issue(
                    severity=Severity.INFO,
                    message=f"被动语态使用较多（约 {len(passive_patterns)} 处）",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence=f"示例: {', '.join(passive_patterns[:5])}",
                    suggestion="过多被动语态会让文章显得生硬。建议适当改用主动语态（如 'We propose...' 代替 'It is proposed that...'）。",
                ))

        # === Academic Ethics Check ===
        full_text = " ".join(tf.raw_text for tf in paper.tex_files)
        full_text_lower = full_text.lower()

        # Check for Ethical Considerations / Broader Impact section
        has_ethics_section = bool(re.search(
            r"\\section\*?\{.*(ethic|broader impact|societal impact|limitation).*\}",
            full_text, re.IGNORECASE
        ))

        # Check if paper involves human subjects
        has_human_annotation = any(phrase in full_text_lower for phrase in [
            "human annotation", "human annotator", "human evaluation",
            "crowdsourc", "mturk", "mechanical turk", "prolific",
            "human judge", "human rater", "inter-annotator",
            "annotation guideline", "annotated by",
        ])

        if has_human_annotation and not has_ethics_section:
            issues.append(Issue(
                severity=Severity.WARNING,
                message="论文涉及人工标注但缺少 Ethical Considerations 章节",
                evidence="检测到人工标注相关内容（human annotation/crowdsourcing/MTurk 等）",
                suggestion="涉及人工标注的论文应包含 Ethical Considerations 或 Broader Impact 章节，说明标注者信息、薪酬等。",
            ))

        # Check if human annotation is mentioned but no annotator profile
        if has_human_annotation:
            has_annotator_info = any(phrase in full_text_lower for phrase in [
                "annotator profile", "annotator background", "annotator demographic",
                "native speaker", "graduate student", "paid", "compensat",
                "per hour", "hourly", "annotators were",
            ])
            if not has_annotator_info:
                issues.append(Issue(
                    severity=Severity.INFO,
                    message="涉及人工标注但未说明标注者背景信息",
                    suggestion="建议添加标注者 profile（如：专业背景、语言能力、薪酬标准等）。这是 ACL/EMNLP 审稿人常关注的点。",
                ))

        # Check for Limitations section (required by ACL 2023+)
        has_limitations = bool(re.search(
            r"\\section\*?\{.*[Ll]imitation.*\}", full_text
        ))
        # Detect if this is an ACL-family submission (which REQUIRES limitations)
        is_acl_family = bool(re.search(
            r"\\usepackage.*\b(?:acl|emnlp|naacl|eacl|coling)\b", full_text, re.IGNORECASE
        )) or bool(re.search(r"acl_natbib|acl2\d{3}|acl-anthology", full_text, re.IGNORECASE))

        if not has_limitations and len(full_text) > 5000:
            if is_acl_family:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message="缺少 Limitations 章节（ACL/EMNLP/NAACL 强制要求）",
                    suggestion="自 ACL 2023 起，所有 *ACL 投稿必须包含 Limitations 章节（不计入页数限制）。"
                    "请在 References 之前添加 \\section*{Limitations}，讨论方法的局限性、适用范围等。"
                    "缺少此章节可能直接导致 desk reject。",
                ))
            else:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message="未找到 Limitations 章节",
                    suggestion="建议添加 Limitations 章节，讨论方法的局限性。"
                    "越来越多的会议（ACL/NeurIPS/ICML）要求或建议包含此章节。",
                ))

        # === Cross-file checks ===
        # Abstract vs Conclusion duplication
        abstract_text = ""
        conclusion_text = ""
        for tex_file in paper.tex_files:
            text = tex_file.raw_text
            # Extract abstract
            abs_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", text, re.DOTALL)
            if abs_match:
                abstract_text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", abs_match.group(1))
                abstract_text = re.sub(r"[\\{}$%]", "", abstract_text).strip()
            # Extract conclusion
            conc_match = re.search(r"\\section\*?\{[Cc]onclusion.*?\}(.*?)(?=\\section|\\end\{document\}|$)", text, re.DOTALL)
            if conc_match:
                conclusion_text = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", conc_match.group(1))
                conclusion_text = re.sub(r"[\\{}$%]", "", conclusion_text).strip()

        if abstract_text and conclusion_text and len(abstract_text) > 100 and len(conclusion_text) > 100:
            sim = SequenceMatcher(None, abstract_text[:500], conclusion_text[:500]).ratio()
            if sim > 0.60:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Abstract 与 Conclusion 内容高度重复（{sim:.0%} 相似）",
                    evidence=f"Abstract: {abstract_text[:80]}...\nConclusion: {conclusion_text[:80]}...",
                    suggestion="Abstract 和 Conclusion 不应过度重复。Conclusion 应总结贡献和未来方向，而非重述 Abstract。",
                ))

        # "et al" formatting check (should be "et al." with period, or \etal in italics)
        for tex_file in paper.tex_files:
            lines = tex_file.raw_text.split("\n")
            etal_issues = 0
            for i, line in enumerate(lines, 1):
                # Check for "et al" without period and not as a LaTeX command
                if re.search(r"\bet al\b(?!\.)", line) and "\\etal" not in line:
                    etal_issues += 1
                    if etal_issues <= 1:  # Only report first instance
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            message="\"et al\" 格式不规范（应为 \"et al.\" 带句点）",
                            location=f"{tex_file.path.name}:{i}",
                            file=tex_file.path.name,
                            line=i,
                            evidence=line.strip()[:80],
                            suggestion="标准格式为 \"et al.\"（带句点）。建议使用 \\textit{et al.} 或定义 \\newcommand{\\etal}{\\textit{et al.}}",
                        ))

        # === Missing Required Sections ===
        self._check_required_sections(paper.tex_files, issues)

        # Compute score
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warn_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        score = max(0, 100 - error_count * 20 - warn_count * 5)
        passed = error_count == 0

        # Generate writing tips based on detected patterns
        tips = []
        for issue in issues:
            if "被动语态" in issue.message:
                tips.append("多用主动语态（We propose/show/demonstrate）提升文章力度")
            elif "超长句子" in issue.message:
                tips.append("长句拆短：一句一个核心观点，控制在 25 词以内")
            elif "em-dash" in issue.message.lower() or "en-dash" in issue.message.lower():
                tips.append("减少 em-dash (—) 使用，改用逗号或分句")
            elif "重复" in issue.message and "段落" in issue.message:
                tips.append("Abstract 和 Conclusion 避免大段复制粘贴，用不同角度总结")
            elif "Limitations" in issue.message:
                tips.append("Limitations 不是缺点列表，而是诚实讨论方法的适用边界")
        # Deduplicate
        tips = list(dict.fromkeys(tips))[:5]

        # Compute writing grade
        grade = "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D"

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=score,
            issues=issues,
            summary=f"写作检查: {error_count} 个错误, {warn_count} 个警告 (Grade {grade})",
            metadata={"grade": grade, "error_count": error_count, "warning_count": warn_count, "tips": tips},
        )

    @staticmethod
    def _extract_paragraphs(text: str) -> list[dict]:
        """Extract paragraphs (text blocks separated by blank lines)."""
        paragraphs = []
        lines = text.split("\n")
        current = []
        start_line = 1

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip LaTeX commands that start blocks
            if stripped.startswith("\\") and any(stripped.startswith(c) for c in
                ["\\begin", "\\end", "\\section", "\\subsection", "\\label",
                 "\\caption", "\\usepackage", "\\documentclass", "\\title"]):
                if current:
                    text_block = " ".join(current)
                    if len(text_block) > 50:
                        paragraphs.append({"text": text_block, "line": start_line})
                    current = []
                continue

            if not stripped:
                if current:
                    text_block = " ".join(current)
                    if len(text_block) > 50:
                        paragraphs.append({"text": text_block, "line": start_line})
                    current = []
            else:
                if not current:
                    start_line = i
                current.append(stripped)

        if current:
            text_block = " ".join(current)
            if len(text_block) > 50:
                paragraphs.append({"text": text_block, "line": start_line})

        return paragraphs

    @staticmethod
    def _check_required_sections(tex_files: list, issues: list):
        """Check for required sections based on detected conference."""
        for tex_file in tex_files:
            if not tex_file.is_main:
                continue
            text = tex_file.raw_text
            text_lower = text.lower()

            # Detect if ACL-family
            is_acl = bool(re.search(
                r"\\usepackage.*\b(?:acl|emnlp|naacl|eacl|coling)\b", text, re.IGNORECASE
            )) or bool(re.search(r"acl_natbib|acl2\d{3}", text, re.IGNORECASE))

            # ACL-family specific requirements
            if is_acl:
                # Check for Ethics Statement (encouraged since ACL 2021)
                has_ethics = bool(re.search(
                    r"\\section\*?\{.*(?:ethic|broader impact).*\}", text, re.IGNORECASE
                ))
                if not has_ethics:
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        message="建议添加 Ethics Statement 章节",
                        location=tex_file.path.name,
                        file=tex_file.path.name,
                        suggestion="ACL 鼓励包含 Ethics Statement（不计入页数）。如涉及人类受试者、偏见分析或潜在误用，建议添加。",
                    ))

            # Check for abstract (universal requirement)
            if not re.search(r"\\begin\{abstract\}", text_lower):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message="缺少 Abstract",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    suggestion="所有学术论文必须包含 Abstract。请添加 \\begin{abstract}...\\end{abstract}。",
                ))
