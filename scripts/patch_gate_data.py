"""Patch gate_data.py with multicolumn support + new claim patterns."""
import ast
import re

with open("app/checks/gate_data.py", encoding="utf-8") as f:
    src = f.read()

# ─────────────────────────────────────────────────────────────────────────────
# 1. Replace _clean_cell_text + add _expand_multicolumn / _is_section_separator
# ─────────────────────────────────────────────────────────────────────────────
NEW_HELPERS = r'''def _clean_cell_text(cell: str) -> str:
    """Strip LaTeX markup from a cell, returning plain text.

    Handles NLP/ML table patterns: progressbar macros, multirow, 62.8\%, thin space.
    """
    # Progress bar and medal macros: keep the numeric argument
    cell = re.sub(r"\\(?:progressbar\w*|goldmedal|silvermedal|bronzemedal)\{([^}]*)\}", r"\1", cell)
    # \multirow{n}{w}{text} -> text
    cell = re.sub(r"\\multirow\{[^}]*\}\{[^}]*\}\{([^}]*)\}", r"\1", cell)
    # \hspace / \vspace -> space
    cell = re.sub(r"\\[hv]space\*?\{[^}]*\}", " ", cell)
    # \quad etc -> space
    cell = re.sub(r"\\(?:quad|qquad|enspace)\b", " ", cell)
    # Strip \% (percent sign) and \, (thin space)
    cell = cell.replace(r"\%", "").replace(r"\,", " ")
    # Strip rank suffix: "62.8 (1)" -> "62.8"
    cell = re.sub(r"(\d)\s*\(\d+\)\s*$", r"\1", cell.strip())
    # Keep content of standard formatting commands
    cell = re.sub(
        r"\\(?:textbf|textit|emph|mathbf|mathrm|text|footnotesize|small|bf|it)\{([^}]*)\}",
        r"\1", cell,
    )
    # Drop remaining LaTeX commands
    cell = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", cell)
    cell = re.sub(r"\\[a-zA-Z@]+\*?", "", cell)
    cell = cell.replace("{", "").replace("}", "").replace("$", "").replace("\\", "")
    return cell.strip()


def _expand_multicolumn(cells: list) -> list:
    """Expand \\multicolumn{N}{spec}{text} into N cells (first has text, rest empty)."""
    MC_PAT = re.compile(
        r"\\multicolumn\{(\d+)\}\{[^}]*\}\{((?:[^{}]|\{[^{}]*\})*)\}", re.DOTALL
    )
    expanded = []
    for cell in cells:
        m = MC_PAT.match(cell.strip())
        if m:
            n = max(1, int(m.group(1)))
            text = _clean_cell_text(m.group(2))
            expanded.append(text)
            expanded.extend([""] * (n - 1))
        else:
            expanded.append(cell)
    return expanded


def _is_section_separator(cells: list) -> bool:
    """True for rows like \\multicolumn{N}{l}{\\textit{Group}} -- table section headers."""
    non_empty = [c.strip() for c in cells if c.strip()]
    if len(non_empty) != 1:
        return False
    cell = non_empty[0]
    return bool(
        re.match(r"\\multicolumn\{", cell)
        and re.search(r"\\textit\{|\\itshape|\\emph\{", cell)
    )

'''

marker = "def _clean_cell_text(cell: str) -> str:"
end_marker = "\ndef _is_header_row"
start = src.index(marker)
end = src.index(end_marker, start)
src = src[:start] + NEW_HELPERS + src[end:]
print("Step 1: replaced _clean_cell_text + added helpers")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Replace row-splitting / header-detection block in _extract_tables
# ─────────────────────────────────────────────────────────────────────────────
NEW_PARSE = (
    "            # --- Split into raw rows (skip rule lines) ---\n"
    "            raw_rows: list[list[str]] = []\n"
    '            for chunk in tabular_body.split("\\\\\\\\"):\n'
    "                for sub in chunk.splitlines():\n"
    "                    sub = sub.strip()\n"
    "                    if not sub:\n"
    "                        continue\n"
    '                    if re.match(r"\\\\(?:hline|toprule|midrule|bottomrule|cline|hdashline|cmidrule)", sub):\n'
    "                        continue\n"
    '                    cells = [c.strip() for c in sub.split("&")]\n'
    "                    cells = _expand_multicolumn(cells)\n"
    "                    if any(c for c in cells):\n"
    "                        raw_rows.append(cells)\n"
    "\n"
    "            if not raw_rows:\n"
    "                continue\n"
    "\n"
    "            # --- Collect header rows: consecutive leading all-text rows ---\n"
    "            # Multi-line headers (multirow/multicolumn) are merged column-by-column.\n"
    "            col_headers: list[str] = []\n"
    "            header_row_count = 0\n"
    "            for row in raw_rows:\n"
    "                if _is_section_separator(row):\n"
    "                    break\n"
    "                if _is_header_row(row):\n"
    "                    header_row_count += 1\n"
    "                    if not col_headers:\n"
    "                        col_headers = [_clean_cell_text(c) for c in row]\n"
    "                    else:\n"
    "                        for i, c in enumerate(row):\n"
    "                            cleaned = _clean_cell_text(c)\n"
    "                            if i < len(col_headers):\n"
    "                                if cleaned and not col_headers[i]:\n"
    "                                    col_headers[i] = cleaned\n"
    "                                elif cleaned and col_headers[i]:\n"
    "                                    col_headers[i] += \" \" + cleaned\n"
    "                            else:\n"
    "                                col_headers.append(cleaned)\n"
    "                else:\n"
    "                    break\n"
    "\n"
    "            data_raw_rows = raw_rows[header_row_count:]"
)

# Find the old block using the em-dash-free comment line
marker2 = "            # --- Split into raw rows (skip rule lines) ---"
end_marker2 = "                data_raw_rows = raw_rows[1:]"
start2 = src.index(marker2)
end2 = src.index(end_marker2, start2) + len(end_marker2)
src = src[:start2] + NEW_PARSE + src[end2:]
print("Step 2: replaced row-parsing block")

# ─────────────────────────────────────────────────────────────────────────────
# 3. Add from_to_pat and direct_metric_pat after comparative_pat
# ─────────────────────────────────────────────────────────────────────────────
EXTRA_PATS = (
    "\n"
    "        # 'improves X from A to B' -- emit destination value B\n"
    "        from_to_pat = re.compile(\n"
    '            r"(?:improv|increas|reduc|decreas|boost|drop|fall|rise)\\w*"\n'
    '            r"(?:\\s+\\w+){0,4}?\\s+from\\s+(\\d+\\.?\\d*)\\s*(?:%|pp)?"\n'
    '            r"\\s+to\\s+(\\d+\\.?\\d*)\\s*(?:%|pp)?",\n'
    "            re.IGNORECASE,\n"
    "        )\n"
    "        # '62.8% accuracy' -- direct value + metric in same phrase\n"
    "        direct_metric_pat = re.compile(\n"
    '            r"(\\d+\\.?\\d*)\\s*(?:\\\\,)?\\s*(?:%|pp)?\\s*"\n'
    '            r"(?:accuracy|acc\\b|f1\\b|f-1\\b|precision\\b|recall\\b|bleu\\b|rouge\\b|"\n'
    '            r"exact\\s+match\\b|em\\b|ndcg\\b|mrr\\b|auc\\b|wer\\b|cer\\b)",\n'
    "            re.IGNORECASE,\n"
    "        )"
)

# Insert after the closing ) of comparative_pat
marker3_start = "        comparative_pat = re.compile("
idx3 = src.index(marker3_start)
# Find the matching closing ')' of this re.compile(...)
paren_depth = 0
i = idx3
while i < len(src):
    if src[i] == "(":
        paren_depth += 1
    elif src[i] == ")":
        paren_depth -= 1
        if paren_depth == 0:
            break
    i += 1
end3 = i + 1  # position after closing )
src = src[:end3] + EXTRA_PATS + src[end3:]
print("Step 3: added from_to_pat and direct_metric_pat")

# ─────────────────────────────────────────────────────────────────────────────
# 4. Add new claim extraction loops after the comparative loop
# ─────────────────────────────────────────────────────────────────────────────
NEW_LOOPS = (
    "\n"
    "                # 'from A to B' -- emit destination value B\n"
    "                for m in from_to_pat.finditer(line):\n"
    "                    try:\n"
    "                        v_to = float(m.group(2))\n"
    "                    except ValueError:\n"
    "                        continue\n"
    "                    if v_to == 0 or v_to > 10_000:\n"
    "                        continue\n"
    "                    vs = m.group(2)\n"
    '                    dp = len(vs.split(".")[1]) if "." in vs else 0\n'
    "                    claims.append({\n"
    '                        "value": v_to, "value_str": vs, "dp": dp,\n'
    '                        "claim_type": "absolute", "delta": None,\n'
    '                        "scope": _scope_from_window(window),\n'
    '                        "file": tex_file.path.name, "line": lineno,\n'
    '                        "context": stripped[:80],\n'
    "                    })\n"
    "\n"
    "                # '62.8% accuracy' -- direct metric-value assertion\n"
    "                for m in direct_metric_pat.finditer(line):\n"
    "                    try:\n"
    "                        v = float(m.group(1))\n"
    "                    except ValueError:\n"
    "                        continue\n"
    "                    if v == 0 or v > 10_000:\n"
    "                        continue\n"
    "                    vs = m.group(1)\n"
    '                    dp = len(vs.split(".")[1]) if "." in vs else 0\n'
    "                    metric_word = m.group(0).lower().split()[-1].rstrip(\".\")\n"
    "                    sc = _scope_from_window(window)\n"
    '                    if not sc.get("metric"):\n'
    '                        sc["metric"] = metric_word\n'
    "                    claims.append({\n"
    '                        "value": v, "value_str": vs, "dp": dp,\n'
    '                        "claim_type": "absolute", "delta": None,\n'
    '                        "scope": sc,\n'
    '                        "file": tex_file.path.name, "line": lineno,\n'
    '                        "context": stripped[:80],\n'
    "                    })"
)

# Find "        return claims" that ends _extract_claims
marker4 = "        return claims\n\n    @staticmethod\n    def _scope_sim"
idx4 = src.index(marker4)
src = src[:idx4] + NEW_LOOPS + "\n\n" + src[idx4:]
print("Step 4: added from_to and direct_metric loops")

# ─────────────────────────────────────────────────────────────────────────────
# Write and verify
# ─────────────────────────────────────────────────────────────────────────────
with open("app/checks/gate_data.py", "w", encoding="utf-8") as f:
    f.write(src)

try:
    ast.parse(src.encode("utf-8"))
    print("\nparse OK")
except SyntaxError as e:
    print(f"\nSyntaxError at line {e.lineno}: {e.msg}")
    lines = src.split("\n")
    for i, l in enumerate(lines[e.lineno - 3 : e.lineno + 3], e.lineno - 2):
        print(f"  {i}: {repr(l[:90])}")
