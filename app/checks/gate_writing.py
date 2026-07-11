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


# AI signature words/phrases — only near-certain signals kept as WARNING triggers.
# Phrases that appear in normal academic writing are demoted or removed to reduce
# false positives on non-native English writers (see Liang et al. 2023, Patterns).
_AI_MARKERS = [
    "as an ai",
    "as a language model",
    "i can't help",
    "here is a summary",
    "here's a summary",
    "certainly!",
    "absolutely!",
    "of course!",
    "sure!",
    "i'd be happy to",
    "i would be happy to",
]

# Words that GPT overuses relative to academic writing — but individually common
# enough to appear in legitimate papers.  Kept as a soft signal: only fire when
# the COMBINED count is very high (≥20), and report as INFO not WARNING.
_AI_CONNECTOR_WORDS = [
    "delve", "delving",
    "leverage", "leveraging",
    "utilize", "utilizing", "utilization",
    "facilitate", "facilitating",
    "comprehensive", "comprehensively",
    "multifaceted",
    "paradigm",
    "henceforth",
]

# These words are more distinctive of AI padding; keep as WARNING at a lower threshold.
_AI_STRONG_MARKERS = [
    "it's worth noting that",
    "it is worth noting that",
    "needless to say",
    "it goes without saying that",
    "in today's rapidly",
    "in today's ever-",
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

# Placeholder / template-remnant strings that should never appear in a real submission
_TEMPLATE_REMNANTS = [
    "lorem ipsum",
    "your paper title",
    "author name",
    "author names",
    "institution name",
    "university name",
    "city, country",
    "your abstract here",
    "insert abstract",
    "todo:",
    "fixme:",
    "xxx:",
    "fill in",
    "tbd",
    "[citation needed]",
    "[figure here]",
    "[table here]",
    "[results here]",
    "anonymous authors",
    "blind submission",
    "under review",
    "do not cite",
    "do not distribute",
    "unpublished manuscript",
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
    description = "Writing quality: detects AI traces, duplicate paragraphs, anonymity issues, and typos"
    is_blocking = False  # Warning level

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []

        for tex_file in paper.tex_files:
            if not tex_file.is_main and not tex_file.raw_text.strip():
                continue
            raw_text = tex_file.raw_text
            text = self._text_layer(raw_text)
            lines = text.split("\n")

            # === AI Trace Detection ===
            # 1. Em-dash count
            em_dash_count = text.count("—") + text.count("---")
            if em_dash_count > 8:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Excessive em-dash (—) usage: {em_dash_count} occurrences",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="GPT-generated text tends to overuse em-dashes. They are relatively rare in academic writing.",
                    suggestion="Consider replacing some em-dashes with commas, semicolons, or parentheses.",
                ))

            # 1.5 En-dash misuse (using -- where - should be, or vice versa)
            en_dash_count = text.count("–") + text.count("--")
            if en_dash_count > 20:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Frequent en-dash (–/--) usage: {en_dash_count} occurrences",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="A high en-dash count may indicate inconsistent formatting. In academic writing, en-dashes are mainly used for numeric ranges (e.g. pages 1--10).",
                    suggestion="Verify that en-dash usage is correct. Use -- for numeric ranges and --- for em-dashes.",
                ))

            # 2. AI connector word frequency — soft signal, report as INFO only
            # when combined count is very high, to reduce false positives on
            # non-native writers (Liang et al. 2023, Patterns).
            text_lower = text.lower()
            ai_word_count = 0
            found_ai_words = []
            for word in _AI_CONNECTOR_WORDS:
                count = text_lower.count(word)
                if count > 0:
                    ai_word_count += count
                    found_ai_words.append(f"{word}({count})")

            if ai_word_count >= 20:
                issues.append(Issue(
                    severity=Severity.INFO,
                    message=f"High frequency of GPT-characteristic words: {ai_word_count} total occurrences",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence=f"High-frequency words: {', '.join(found_ai_words[:8])}",
                    suggestion="These words appear at elevated rates in AI-generated text, but may also occur in legitimate academic writing. Provided for reference only — not a definitive judgment.",
                ))

            # 2.5 Strong AI padding phrases — higher confidence, report as WARNING
            strong_count = 0
            strong_examples = []
            for i, line in enumerate(lines, 1):
                ll = line.lower()
                for pat in _AI_STRONG_MARKERS:
                    if pat in ll and not line.strip().startswith("%"):
                        strong_count += 1
                        if len(strong_examples) < 3:
                            strong_examples.append(f"L{i}: {line.strip()[:70]}")
                        break
            if strong_count >= 3:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Detected {strong_count} AI-characteristic filler phrases",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="\n".join(strong_examples),
                    suggestion="These phrases are highly typical of AI-generated text. Consider replacing them with more specific language.",
                ))

            # 3. Prompt leakage — only fire when not inside quotes or citations
            _QUOTE_RE = re.compile(
                r"``.*?''|\".*?\"|`.*?'|\{[^}]*\}|\[.*?\]|https?://\S+",
                re.DOTALL,
            )
            for i, line in enumerate(lines, 1):
                line_lower = line.lower()
                for marker in _AI_MARKERS:
                    if marker not in line_lower:
                        continue
                    stripped = line.strip()
                    if stripped.startswith("%"):
                        break
                    masked = _QUOTE_RE.sub("", line_lower)
                    if marker not in masked:
                        break
                    ctx_words = {"response:", "output:", "example:", "replies:", "generated:",
                                 "answered:", "replied:", "query:", "prompt:", "caption:"}
                    prev_lines = lines[max(0, i-3):i-1]
                    prev_text = " ".join(prev_lines).lower()
                    if any(w in prev_text for w in ctx_words):
                        break
                    if line.count("&") >= 2 or line.count("\\\\") >= 1:
                        break
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"Possible AI prompt leakage: \"{marker}\"",
                        location=f"{tex_file.path.name}:{i}",
                        file=tex_file.path.name,
                        line=i,
                        evidence=line.strip()[:100],
                        suggestion="This text contains clear signs of AI generation. Please remove or rewrite it.",
                    ))
                    break

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
                            message=f"Two paragraphs are highly similar ({sim:.0%})",
                            location=f"{tex_file.path.name}:{paragraphs[i]['line']}",
                            file=tex_file.path.name,
                            line=paragraphs[i]["line"],
                            evidence=f"Paragraph 1 (line {paragraphs[i]['line']}): {paragraphs[i]['text'][:60]}...\nParagraph 2 (line {paragraphs[j]['line']}): {paragraphs[j]['text'][:60]}...",
                            suggestion="These two paragraphs are nearly identical, which may be a copy-paste artifact. Check whether one should be removed or rewritten.",
                        ))

            # === Anonymization Check ===
            # Check for [final] mode in ACL/EMNLP templates (should be [review] for double-blind)
            final_match = re.search(r"\\usepackage\[final\]\{(acl|emnlp|naacl|eacl|coling)\}", raw_text)
            if final_match:
                line_num = raw_text[:final_match.start()].count("\n") + 1
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message="Submission mode is [final]; double-blind review should use [review]",
                    location=f"{tex_file.path.name}:{line_num}",
                    file=tex_file.path.name,
                    line=line_num,
                    evidence=final_match.group(0),
                    suggestion=f"Change \\usepackage[final]{{{final_match.group(1)}}} to \\usepackage[review]{{{final_match.group(1)}}} to enable anonymous mode.",
                ))

            # Check \author{} content (only warn if [final] mode detected)
            author_match = re.search(r"\\author\{(.+?)\}", raw_text, re.DOTALL)
            author_content = ""
            if author_match:
                author_content = author_match.group(1).strip()

            # Check for PDF metadata leaking author info (\hypersetup, \pdfinfo)
            hypersetup = re.search(r"\\hypersetup\{(.*?)\}", raw_text, re.DOTALL)
            if hypersetup:
                hs_content = hypersetup.group(1)
                if re.search(r"pdfauthor\s*=", hs_content, re.IGNORECASE):
                    line_num = raw_text[:hypersetup.start()].count("\n") + 1
                    issues.append(Issue(
                        severity=Severity.WARNING,
                        message="\\hypersetup contains pdfauthor (PDF metadata leaks author identity)",
                        location=f"{tex_file.path.name}:{line_num}",
                        file=tex_file.path.name,
                        line=line_num,
                        evidence=hs_content.strip()[:80],
                        suggestion="Remove the pdfauthor field from \\hypersetup before double-blind submission.",
                    ))

            # Check for self-citation patterns
            for i, line in enumerate(lines, 1):
                for pat in _SELF_CITE_PATTERNS:
                    if re.search(pat, line, re.IGNORECASE):
                        issues.append(Issue(
                            severity=Severity.WARNING,
                            message="Self-referential phrasing may reveal author identity",
                            location=f"{tex_file.path.name}:{i}",
                            file=tex_file.path.name,
                            line=i,
                            evidence=line.strip()[:100],
                            suggestion="In double-blind submissions, avoid phrases like 'our previous work' that expose author identity. Consider using 'Prior work [X]' instead.",
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
                body_start = raw_text.find("\\begin{document}")
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
                            message=f"Author surname(s) appear in the body text: {', '.join(found_names)}",
                            location=tex_file.path.name,
                            file=tex_file.path.name,
                            evidence=f"Detected surname(s): {', '.join(found_names)} (may reveal author identity)",
                            suggestion="In double-blind submissions, author names should not appear in the body. Check whether these occur in a self-citation context.",
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
                    message=f"Found {len(typo_found)} spelling error(s)",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence=evidence,
                    suggestion="Please correct the spelling errors listed above.",
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
                if wrong in raw_text:
                    found_latex_typos.append(f"{wrong} → {right}")

            if found_latex_typos:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"LaTeX command typo(s): {len(found_latex_typos)} found",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="\n".join(f"  {t}" for t in found_latex_typos),
                    suggestion="These misspelled commands will cause compilation failure. Please fix them.",
                ))

            # Template remnant detection — placeholder text left in from a template
            remnant_found = []
            text_lower_full = raw_text.lower()
            for remnant in _TEMPLATE_REMNANTS:
                if remnant in text_lower_full:
                    # Find line number
                    idx = text_lower_full.find(remnant)
                    rline = raw_text[:idx].count("\n") + 1
                    remnant_found.append(f"L{rline}: \"{remnant}\"")
            if remnant_found:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"Found {len(remnant_found)} template remnant(s) / placeholder text",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="\n".join(remnant_found[:6]),
                    suggestion="All template placeholder text (e.g. 'Lorem ipsum', 'TODO:', '[citation needed]') must be removed before submission.",
                ))

            # Double spaces (cosmetic but sloppy)
            double_space_lines = [i for i, line in enumerate(lines, 1)
                                  if "  " in line and not line.strip().startswith("%")]
            if len(double_space_lines) > 30:
                issues.append(Issue(
                    severity=Severity.INFO,
                    message=f"Found {len(double_space_lines)} lines containing extra double spaces",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    suggestion="While this does not affect compilation, double spaces are non-standard. Use a regex find-and-replace in your editor to clean them up.",
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

            if filler_count >= 8:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Detected {filler_count} filler / boilerplate sentence(s)",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence="\n".join(filler_examples),
                    suggestion="These sentences are common in AI-generated or padded text and add little substance. Consider removing or replacing them with concrete discussion.",
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

            if long_sentences > 10:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"Found {long_sentences} overly long sentence(s) (>50 words); longest is {longest_line_words} words at line {longest_line_num}",
                    location=f"{tex_file.path.name}:{longest_line_num}",
                    file=tex_file.path.name,
                    line=longest_line_num,
                    evidence=f"Longest sentence: {longest_line[:100]}...",
                    suggestion="Overly long sentences hurt readability. Consider splitting them into shorter sentences of 20–30 words each. Click to jump to the longest one.",
                ))

            # 2. Passive voice overuse (simple heuristic)
            passive_patterns = re.findall(
                r"\b(?:is|are|was|were|been|being)\s+\w+ed\b",
                text, re.IGNORECASE
            )
            if len(passive_patterns) > 35:
                issues.append(Issue(
                    severity=Severity.INFO,
                    message=f"Passive voice used frequently (approximately {len(passive_patterns)} instances)",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    evidence=f"Examples: {', '.join(passive_patterns[:5])}",
                    suggestion="Excessive passive voice can make writing feel stilted. Consider switching to active voice where appropriate (e.g. 'We propose...' instead of 'It is proposed that...').",
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
                message="Paper involves human annotation but lacks an Ethical Considerations section",
                evidence="Human annotation-related content detected (human annotation/crowdsourcing/MTurk, etc.)",
                suggestion="Papers involving human annotation should include an Ethical Considerations or Broader Impact section describing annotator details, compensation, etc.",
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
                    message="Human annotation is mentioned but annotator background is not described",
                    suggestion="Consider adding an annotator profile (e.g. professional background, language proficiency, compensation). This is a point reviewers at ACL/EMNLP often scrutinize.",
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
                    message="Missing Limitations section (required by ACL/EMNLP/NAACL)",
                    suggestion="Since ACL 2023, all *ACL submissions must include a Limitations section (not counted toward the page limit). "
                    "Add \\section*{Limitations} before References to discuss the scope and limitations of your method. "
                    "Omitting this section may result in a desk rejection.",
                ))
            else:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message="No Limitations section found",
                    suggestion="Consider adding a Limitations section to discuss the constraints of your method. "
                    "An increasing number of venues (ACL/NeurIPS/ICML) require or strongly encourage this section.",
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
                    message=f"Abstract and Conclusion overlap significantly ({sim:.0%} similarity)",
                    evidence=f"Abstract: {abstract_text[:80]}...\nConclusion: {conclusion_text[:80]}...",
                    suggestion="The Abstract and Conclusion should not be excessively repetitive. The Conclusion should summarize contributions and future directions rather than restating the Abstract.",
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
                            message="\"et al\" format is incorrect (should be \"et al.\" with a period)",
                            location=f"{tex_file.path.name}:{i}",
                            file=tex_file.path.name,
                            line=i,
                            evidence=line.strip()[:80],
                            suggestion="The standard format is \"et al.\" (with a period). Consider using \\textit{et al.} or defining \\newcommand{\\etal}{\\textit{et al.}}",
                        ))

        # === Missing Required Sections ===
        self._check_required_sections(paper.tex_files, issues)

        # Compute score
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)
        warn_count = sum(1 for i in issues if i.severity == Severity.WARNING)
        # Cap warnings contribution so a large paper with many minor warnings
        # doesn't collapse to 0. Warnings beyond 10 have diminishing weight.
        warn_penalty = min(warn_count, 10) * 5 + max(0, warn_count - 10) * 1
        score = max(0, 100 - error_count * 20 - warn_penalty)
        passed = error_count == 0

        # Generate writing tips based on detected patterns
        tips = []
        for issue in issues:
            if "passive voice" in issue.message.lower():
                tips.append("Use active voice (We propose/show/demonstrate) to strengthen your writing")
            elif "overly long sentence" in issue.message.lower() or "long sentence" in issue.message.lower():
                tips.append("Break long sentences: one core idea per sentence, aim for under 25 words")
            elif "em-dash" in issue.message.lower() or "en-dash" in issue.message.lower():
                tips.append("Reduce em-dash (—) usage; replace with commas or split into clauses")
            elif "similar" in issue.message.lower() and "paragraph" in issue.message.lower():
                tips.append("Avoid copying large blocks between Abstract and Conclusion; summarize from a different angle")
            elif "Limitations" in issue.message:
                tips.append("A Limitations section is not a list of weaknesses — discuss the applicable scope of your method honestly")
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
            summary=f"Writing check: {error_count} error(s), {warn_count} warning(s) (Grade {grade})",
            metadata={"grade": grade, "error_count": error_count, "warning_count": warn_count, "tips": tips},
        )

    @staticmethod
    def _text_layer(raw_text: str) -> str:
        """Return approximate prose text while preserving line count.

        Writing-quality heuristics should not fire on comments, bibliography,
        code/listings, or LaTeX command names. This lightweight layer keeps
        line numbers broadly stable by replacing removed content with blanks.
        """
        lines = []
        in_ignored_env = False
        ignored_envs = ("bibliography", "thebibliography", "verbatim", "lstlisting", "minted")

        for line in raw_text.split("\n"):
            stripped = line.strip()
            if any(re.search(rf"\\begin\{{{env}\}}", stripped) for env in ignored_envs):
                in_ignored_env = True
                lines.append("")
                continue
            if in_ignored_env:
                if any(re.search(rf"\\end\{{{env}\}}", stripped) for env in ignored_envs):
                    in_ignored_env = False
                lines.append("")
                continue

            # Remove unescaped comments.
            no_comment = ""
            i = 0
            while i < len(line):
                if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                    break
                no_comment += line[i]
                i += 1

            # Keep command arguments but drop command names/options.
            no_command = re.sub(r"\\[a-zA-Z]+\*?(?:\s*\[[^\]]*\])?", " ", no_comment)
            no_command = re.sub(r"[{}$\\]", " ", no_command)
            lines.append(no_command)

        return "\n".join(lines)

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
                        message="Consider adding an Ethics Statement section",
                        location=tex_file.path.name,
                        file=tex_file.path.name,
                        suggestion="ACL encourages including an Ethics Statement (not counted toward the page limit). If the paper involves human subjects, bias analysis, or potential misuse, this section is recommended.",
                    ))

            # Check for abstract (universal requirement)
            if not re.search(r"\\begin\{abstract\}", text_lower):
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message="Missing Abstract",
                    location=tex_file.path.name,
                    file=tex_file.path.name,
                    suggestion="All academic papers must include an Abstract. Add \\begin{abstract}...\\end{abstract}.",
                ))
