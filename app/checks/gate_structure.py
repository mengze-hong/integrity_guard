"""Gate 1: Project Structure Integrity.

Verifies that the uploaded project has a valid structure:
1. At least one .tex and one .bib file exist
2. Main .tex can be identified (has \\documentclass + \\begin{document})
3. All \\input{}/\\include{} referenced files exist
4. All \\includegraphics{} referenced images exist
5. All \\bibliography{} referenced .bib files exist
6. No duplicate \\label{} definitions
7. No orphan \\ref{} references
8. No duplicate (copy-pasted) images
"""

import hashlib
import re
from collections import Counter
from pathlib import Path

from app.checks.base import BaseGate
from app.models import CheckResult, Issue, ParsedPaper, Severity, TexFile

_BIBLIOGRAPHY_PATTERN = re.compile(r"\\bibliography\{([^}]+)\}")


class StructureGate(BaseGate):
    """Gate 1: Verify project file structure integrity."""

    name = "structure_integrity"
    description = "文件结构检查：验证项目文件完整性，所有引用的文件都存在"
    is_blocking = True

    async def check(self, paper: ParsedPaper) -> CheckResult:
        issues: list[Issue] = []
        score = 100.0

        # Check 1: .tex files exist
        if not paper.tex_files:
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    message="项目中未找到 .tex 文件",
                    suggestion="请上传包含至少一个 .tex 文件的 LaTeX 项目",
                )
            )
            return CheckResult(
                gate_name=self.name,
                gate_description=self.description,
                passed=False,
                score=0.0,
                issues=issues,
                summary="未找到 .tex 文件",
            )

        # Check 2: .bib file exists
        if not paper.bib_entries and not paper.bib_file_path:
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    message="项目中未找到 .bib 文件",
                    suggestion="请包含 .bib 参考文献文件",
                )
            )
            score -= 50

        # Check 3: Main .tex identified
        main_files = [t for t in paper.tex_files if t.is_main]
        if not main_files:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    message="无法识别主 .tex 文件（未找到 \\documentclass）",
                    suggestion="请确保有一个 .tex 文件包含 \\documentclass 和 \\begin{document}",
                )
            )
            score -= 10

        # Check 4: All \input{} and \include{} files exist
        for tex_file in paper.tex_files:
            for input_ref in tex_file.inputs + tex_file.includes:
                # Resolve relative to tex file's directory or project root
                ref_path = input_ref if input_ref.endswith(".tex") else f"{input_ref}.tex"
                candidates = [
                    tex_file.path.parent / ref_path,
                    paper.project_dir / ref_path,
                ]
                if not any(c.exists() for c in candidates):
                    issues.append(
                        Issue(
                            severity=Severity.ERROR,
                            message=f"引用的文件不存在: \\input{{{input_ref}}}",
                            location=str(tex_file.path.name),
                            suggestion=f"请确保 '{ref_path}' 包含在上传的 zip 中",
                        )
                    )
                    score -= 15

        # Check 5: All \includegraphics{} files exist
        for tex_file in paper.tex_files:
            for graphic in tex_file.graphics:
                # Try with and without common extensions
                candidates = [paper.project_dir / graphic]
                if not Path(graphic).suffix:
                    for ext in [".png", ".pdf", ".jpg", ".jpeg", ".eps"]:
                        candidates.append(paper.project_dir / f"{graphic}{ext}")
                # Also try relative to tex file
                candidates.append(tex_file.path.parent / graphic)

                if not any(c.exists() for c in candidates):
                    issues.append(
                        Issue(
                            severity=Severity.WARNING,
                            message=f"图片文件不存在: {graphic}",
                            location=str(tex_file.path.name),
                            suggestion=f"请将图片文件 '{graphic}' 包含在上传的 zip 中",
                        )
                    )
                    score -= 5

        # Check 5.5: \bibliography{} points to existing .bib file
        for tex_file in paper.tex_files:
            for bib_match in _BIBLIOGRAPHY_PATTERN.finditer(tex_file.raw_text):
                bib_refs = [b.strip() for b in bib_match.group(1).split(",")]
                for bib_ref in bib_refs:
                    bib_name = bib_ref if bib_ref.endswith(".bib") else f"{bib_ref}.bib"
                    candidates = [
                        tex_file.path.parent / bib_name,
                        paper.project_dir / bib_name,
                    ]
                    if not any(c.exists() for c in candidates):
                        issues.append(Issue(
                            severity=Severity.ERROR,
                            message=f"\\bibliography{{{bib_ref}}} 指向不存在的文件: {bib_name}",
                            location=str(tex_file.path.name),
                            file=tex_file.path.name,
                            suggestion=f"请确保 '{bib_name}' 包含在上传的 zip 中，或修正 \\bibliography 中的文件名。",
                        ))
                        score -= 15

        # Check 6: Duplicate \label definitions
        all_labels: dict[str, list[str]] = {}  # label → [files where defined]
        for tex_file in paper.tex_files:
            for label in tex_file.labels:
                if label not in all_labels:
                    all_labels[label] = []
                all_labels[label].append(tex_file.path.name)

        for label, files in all_labels.items():
            if len(files) > 1:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"重复的 \\label{{{label}}}（在 {len(files)} 个文件中定义）",
                    location=", ".join(files),
                    suggestion="每个 label 只能定义一次。重复 label 会导致交叉引用指向错误位置。",
                ))
                score -= 10

        # Check 7: Orphan \ref (references to non-existent labels)
        all_label_set = set(all_labels.keys())
        all_refs: dict[str, list[str]] = {}  # ref_key → [files]
        for tex_file in paper.tex_files:
            for ref in tex_file.refs:
                if ref not in all_refs:
                    all_refs[ref] = []
                all_refs[ref].append(tex_file.path.name)

        for ref_key, files in all_refs.items():
            if ref_key not in all_label_set:
                issues.append(Issue(
                    severity=Severity.ERROR,
                    message=f"\\ref{{{ref_key}}} 引用了不存在的 label",
                    location=files[0],
                    file=files[0],
                    suggestion=f"请创建 \\label{{{ref_key}}} 或修正 \\ref 中的拼写。编译后会显示 '??'。",
                ))
                score -= 10

        # Check 8: Duplicate images (same file content, different name)
        image_exts = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
        image_hashes: dict[str, list[str]] = {}  # hash → [file paths]
        for img_file in paper.project_dir.rglob("*"):
            if img_file.is_file() and img_file.suffix.lower() in image_exts:
                try:
                    h = hashlib.md5(img_file.read_bytes()).hexdigest()
                    rel = str(img_file.relative_to(paper.project_dir))
                    if h not in image_hashes:
                        image_hashes[h] = []
                    image_hashes[h].append(rel)
                except Exception:
                    pass

        for h, paths in image_hashes.items():
            if len(paths) > 1:
                issues.append(Issue(
                    severity=Severity.WARNING,
                    message=f"发现重复图片文件（{len(paths)} 个文件内容完全相同）",
                    location=paths[0],
                    evidence=f"相同文件: {', '.join(paths[:4])}",
                    suggestion="这些图片文件内容完全一样。如果用于不同的 figure，可能是 copy-paste 错误。",
                ))
                score -= 5

        # Check 9: Unmatched \begin{} / \end{} environments
        for tex_file in paper.tex_files:
            text = tex_file.raw_text
            # Strip comments
            clean_lines = []
            for line in text.split("\n"):
                # Remove inline comments (but not \%)
                idx = 0
                while idx < len(line):
                    if line[idx] == '%' and (idx == 0 or line[idx-1] != '\\'):
                        line = line[:idx]
                        break
                    idx += 1
                clean_lines.append(line)
            clean = "\n".join(clean_lines)

            begins = re.findall(r"\\begin\{(\w+)\}", clean)
            ends = re.findall(r"\\end\{(\w+)\}", clean)

            begin_counts = Counter(begins)
            end_counts = Counter(ends)

            for env, count in begin_counts.items():
                end_count = end_counts.get(env, 0)
                if count > end_count:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"\\begin{{{env}}} 比 \\end{{{env}}} 多 {count - end_count} 个（未关闭的环境）",
                        location=tex_file.path.name,
                        file=tex_file.path.name,
                        suggestion=f"请确保每个 \\begin{{{env}}} 都有对应的 \\end{{{env}}}。未关闭的环境会导致编译失败。",
                    ))
                    score -= 15

            for env, count in end_counts.items():
                begin_count = begin_counts.get(env, 0)
                if count > begin_count:
                    issues.append(Issue(
                        severity=Severity.ERROR,
                        message=f"\\end{{{env}}} 比 \\begin{{{env}}} 多 {count - begin_count} 个（多余的结束标记）",
                        location=tex_file.path.name,
                        file=tex_file.path.name,
                        suggestion=f"有多余的 \\end{{{env}}}。请检查是否误删了对应的 \\begin{{{env}}}。",
                    ))
                    score -= 15

        passed = all(i.severity != Severity.ERROR for i in issues)
        error_count = sum(1 for i in issues if i.severity == Severity.ERROR)

        return CheckResult(
            gate_name=self.name,
            gate_description=self.description,
            passed=passed,
            score=max(score, 0.0),
            issues=issues,
            summary=f"结构检查: {error_count} 个错误, {len(issues) - error_count} 个警告",
        )
