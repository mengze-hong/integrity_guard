"""Tests for shared project file-store helpers."""

import zipfile

import pytest
from fastapi import HTTPException

from app.services.file_store import list_editable_files, project_zip_bytes, safe_project_file


def test_safe_project_file_blocks_traversal(tmp_path):
    with pytest.raises(HTTPException):
        safe_project_file(tmp_path, "../escape.tex")


def test_list_editable_files_includes_latex_support_files(tmp_path):
    (tmp_path / "main.tex").write_text("x", encoding="utf-8")
    (tmp_path / "custom.sty").write_text("x", encoding="utf-8")
    (tmp_path / "image.png").write_text("x", encoding="utf-8")

    paths = {item["path"] for item in list_editable_files(tmp_path)}

    assert paths == {"main.tex", "custom.sty"}


def test_project_zip_bytes_preserves_relative_paths(tmp_path):
    subdir = tmp_path / "sections"
    subdir.mkdir()
    (subdir / "intro.tex").write_text("hello", encoding="utf-8")

    buffer = project_zip_bytes(tmp_path)

    with zipfile.ZipFile(buffer) as zf:
        assert zf.namelist() == ["sections/intro.tex"]
