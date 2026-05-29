from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_count_loc_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "count_loc.py"
    spec = importlib.util.spec_from_file_location("count_loc", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_report_counts_languages_and_scripts(tmp_path: Path) -> None:
    module = load_count_loc_module()

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')\n\n# comment\n", encoding="utf-8")
    (tmp_path / "src" / "runner.ps1").write_text("Write-Host 'ok'\n", encoding="utf-8")
    (tmp_path / "src" / "notes.md").write_text("# docs\n", encoding="utf-8")
    ignored_dir = tmp_path / "Acts"
    ignored_dir.mkdir()
    (ignored_dir / "skip.py").write_text("print('skip')\n", encoding="utf-8")

    report = module.build_report(tmp_path, include_markdown=False)

    assert report.scanned_files == 2
    assert report.by_language["Python"].code_lines == 2
    assert report.by_language["Python"].files == 1
    assert report.by_language["PowerShell"].code_lines == 1
    assert report.by_script["Python脚本"].code_lines == 2
    assert report.by_script["PowerShell脚本"].code_lines == 1
    assert "Markdown" not in report.by_language


def test_include_markdown_adds_markdown_language(tmp_path: Path) -> None:
    module = load_count_loc_module()

    (tmp_path / "README.md").write_text("hello\n\nworld\n", encoding="utf-8")

    report = module.build_report(tmp_path, include_markdown=True)

    assert report.scanned_files == 1
    assert report.by_language["Markdown"].code_lines == 2