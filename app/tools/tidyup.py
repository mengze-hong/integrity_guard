"""Project structure tidying tool.

Reorganizes LaTeX project files:
1. Extract long tables from main .tex into floats/tab_*.tex with input
2. Extract long figures from main .tex into floats/fig_*.tex with input
3. Move scattered image files (pdf/png/jpg) into figures/ with clean naming
"""

import re
import shutil
from pathlib import Path

from app.models import TexFile


def analyze_tidyup(project_dir: Path, tex_files: list[TexFile]) -> list[dict]:
    """Analyze what changes would be made without executing them.

    Returns list of proposed changes, each with:
    - type: 'extract_table' | 'extract_figure' | 'move_image'
    - description: human-readable description
    - source: original location
    - target: proposed new location
    - content: the content to be extracted (for table/figure)
    """
    changes = []

    for tex_file in tex_files:
        if not tex_file.is_main:
            continue
        text = tex_file.raw_text
        lines = text.split("\n")

        # 1. Find long table environments (>10 lines)
        table_pattern = re.compile(
            r"(\\begin\{table\*?\}.*?\\end\{table\*?\})", re.DOTALL
        )
        for i, match in enumerate(table_pattern.finditer(text)):
            table_content = match.group(1)
            table_lines = table_content.count("\n") + 1
            if table_lines >= 10:
                # Extract a name from caption or label
                label_match = re.search(r"\\label\{([^}]+)\}", table_content)
                caption_match = re.search(r"\\caption\{(.+?)\}", table_content)

                if label_match:
                    name = label_match.group(1).replace("tab:", "").replace(":", "_")
                else:
                    name = f"table_{i+1}"

                name = re.sub(r"[^\w]", "_", name)[:30]
                target_file = f"floats/tab_{name}.tex"

                start_line = text[:match.start()].count("\n") + 1

                changes.append({
                    "type": "extract_table",
                    "description": f"提取表格到 {target_file}（{table_lines} 行）",
                    "source": f"{tex_file.path.name}:{start_line}",
                    "target": target_file,
                    "content": table_content,
                    "original_text": table_content,
                    "replacement": f"\\input{{{target_file}}}",
                    "file": str(tex_file.path),
                })

        # 2. Find long figure environments (>5 lines)
        figure_pattern = re.compile(
            r"(\\begin\{figure\*?\}.*?\\end\{figure\*?\})", re.DOTALL
        )
        for i, match in enumerate(figure_pattern.finditer(text)):
            fig_content = match.group(1)
            fig_lines = fig_content.count("\n") + 1
            if fig_lines >= 5:
                label_match = re.search(r"\\label\{([^}]+)\}", fig_content)

                if label_match:
                    name = label_match.group(1).replace("fig:", "").replace(":", "_")
                else:
                    name = f"figure_{i+1}"

                name = re.sub(r"[^\w]", "_", name)[:30]
                target_file = f"floats/fig_{name}.tex"

                start_line = text[:match.start()].count("\n") + 1

                changes.append({
                    "type": "extract_figure",
                    "description": f"提取图片环境到 {target_file}（{fig_lines} 行）",
                    "source": f"{tex_file.path.name}:{start_line}",
                    "target": target_file,
                    "content": fig_content,
                    "original_text": fig_content,
                    "replacement": f"\\input{{{target_file}}}",
                    "file": str(tex_file.path),
                })

    # 3. Find scattered image files that should be in figures/
    image_exts = {".png", ".jpg", ".jpeg", ".pdf", ".eps", ".svg"}
    figures_dir = project_dir / "figures"

    for img_file in project_dir.rglob("*"):
        if not img_file.is_file():
            continue
        if img_file.suffix.lower() not in image_exts:
            continue
        # Skip if already in figures/ or floats/
        rel = img_file.relative_to(project_dir)
        rel_parts = rel.parts
        if rel_parts[0] in ("figures", "floats", "images", "img", "figs"):
            continue
        # Skip if in a hidden directory
        if any(p.startswith(".") for p in rel_parts):
            continue

        # Propose moving to figures/
        clean_name = re.sub(r"[^\w.]", "_", img_file.name).lower()
        target = f"figures/{clean_name}"

        changes.append({
            "type": "move_image",
            "description": f"移动图片 {rel} → {target}",
            "source": str(rel),
            "target": target,
            "file": str(img_file),
        })

    return changes


def execute_changes(project_dir: Path, changes: list[dict]) -> list[str]:
    """Execute the approved changes.

    Returns list of executed change descriptions.
    """
    executed = []
    floats_dir = project_dir / "floats"
    figures_dir = project_dir / "figures"

    for change in changes:
        try:
            if change["type"] in ("extract_table", "extract_figure"):
                # Create floats directory
                floats_dir.mkdir(exist_ok=True)

                # Write extracted content to new file
                target_path = project_dir / change["target"]
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(change["content"] + "\n", encoding="utf-8")

                # Replace in source file
                source_path = Path(change["file"])
                source_text = source_path.read_text(encoding="utf-8")
                source_text = source_text.replace(
                    change["original_text"],
                    change["replacement"]
                )
                source_path.write_text(source_text, encoding="utf-8")

                executed.append(change["description"])

            elif change["type"] == "move_image":
                # Create figures directory
                figures_dir.mkdir(exist_ok=True)

                source_path = Path(change["file"])
                target_path = project_dir / change["target"]

                if source_path.exists() and not target_path.exists():
                    shutil.move(str(source_path), str(target_path))
                    executed.append(change["description"])

        except Exception as e:
            continue

    return executed
