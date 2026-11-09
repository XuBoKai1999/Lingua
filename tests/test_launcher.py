from __future__ import annotations

import importlib.metadata
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import types

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("lingua_launcher", ROOT / "run.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_dependency_ranges_missing_old_upper_and_normalized_versions(monkeypatch):
    versions = {"PySide6": "6.6.0", "edge-tts": "7.3.1"}
    monkeypatch.setattr(importlib.metadata, "version", lambda name: versions[name])
    requirements = ["PySide6>=6.6", "edge-tts>=7.3.1,<8"]
    assert not launcher.dependency_problems(requirements)
    for version in ("7.2.8", "8.0", "7.3.1rc1"):
        versions["edge-tts"] = version
        assert launcher.dependency_problems(requirements)[0][0] == requirements[1]

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    assert len(launcher.dependency_problems(requirements)) == 2
    with pytest.raises(ValueError, match="不支援"):
        launcher.dependency_problems(["unknown @ https://example.com"])


@pytest.mark.parametrize("answer", ["n", "", "eof"])
def test_decline_never_installs(monkeypatch, capsys, answer):
    monkeypatch.setattr(launcher.site, "ENABLE_USER_SITE", True)
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda *a: object())

    def respond(prompt):
        if answer == "eof":
            raise EOFError
        return answer

    monkeypatch.setattr("builtins.input", respond)
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **kw: pytest.fail("must not install"))
    assert launcher.install_dependencies([("edge-tts>=7.3.1,<8", "missing")]) == 1
    output = capsys.readouterr().out
    assert launcher.sys.executable in output and "安裝目標" in output and "未安裝" in output


@pytest.mark.parametrize("virtualenv", [False, True])
def test_confirm_install_targets_same_interpreter_and_restarts(monkeypatch, virtualenv):
    monkeypatch.setattr(launcher.site, "ENABLE_USER_SITE", True)
    monkeypatch.setattr(launcher.sys, "prefix", "venv" if virtualenv else launcher.sys.base_prefix)
    monkeypatch.setattr(launcher.sys, "argv", ["run.py"])
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda *a: object())
    monkeypatch.setattr("builtins.input", lambda *a: "yes")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs == {"check": False}
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.install_dependencies([("edge-tts>=7.3.1,<8", "old")]) == 0
    assert calls[0][:4] == [sys.executable, "-m", "pip", "install"]
    assert ("--user" in calls[0]) is (not virtualenv)
    assert calls[0][-1] == "edge-tts>=7.3.1,<8"
    assert calls[1] == [sys.executable, str(ROOT / "run.py"), launcher.AFTER_INSTALL]


def test_install_failure_and_post_install_failure_do_not_loop(monkeypatch, capsys):
    monkeypatch.setattr(launcher.site, "ENABLE_USER_SITE", True)
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda *a: object())
    monkeypatch.setattr("builtins.input", lambda *a: "y")
    calls = []
    monkeypatch.setattr(launcher.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or types.SimpleNamespace(returncode=42))
    problems = [("edge-tts>=7.3.1,<8", "missing")]
    assert launcher.install_dependencies(problems) == 1
    assert len(calls) == 1 and "42" in capsys.readouterr().out
    assert launcher.install_dependencies(problems, after_install=True) == 1
    assert len(calls) == 1 and "不會反覆安裝" in capsys.readouterr().out


def test_disabled_user_site_and_missing_pip(monkeypatch, capsys):
    problems = [("PySide6>=6.6", "missing")]
    monkeypatch.setattr(launcher.sys, "prefix", launcher.sys.base_prefix)
    monkeypatch.setattr(launcher.site, "ENABLE_USER_SITE", False)
    assert launcher.install_dependencies(problems) == 1
    assert "停用" in capsys.readouterr().out
    monkeypatch.setattr(launcher.site, "ENABLE_USER_SITE", True)
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda *a: None)
    assert launcher.install_dependencies(problems) == 1
    assert "沒有 pip" in capsys.readouterr().out


def test_uninstalled_checkout_uses_own_src_not_another_lingua(tmp_path):
    checkout = tmp_path / "checkout with spaces"
    package = checkout / "src" / "lingua"
    package.mkdir(parents=True)
    shutil.copy2(ROOT / "run.py", checkout / "run.py")
    shutil.copy2(ROOT / "pyproject.toml", checkout / "pyproject.toml")
    # Tiny app stub isolates source resolution from Qt installation.
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "app.py").write_text("def main():\n    print('CHECKOUT_APP')\n    return 0\n", encoding="utf-8")
    alien = tmp_path / "unrelated" / "lingua"
    alien.mkdir(parents=True)
    (alien / "__init__.py").write_text("raise RuntimeError('WRONG_LINGUA')", encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(alien.parent), "PYTHONDONTWRITEBYTECODE": "1"}
    wrapper = (
        "import importlib.metadata as m,runpy,sys; "
        "m.version=lambda n: {'PySide6':'6.6.0','edge-tts':'7.3.1'}[n]; "
        "runpy.run_path(sys.argv[1],run_name='__main__')"
    )
    result = subprocess.run([sys.executable, "-S", "-c", wrapper, str(checkout / "run.py")], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "CHECKOUT_APP"


def test_clean_interpreter_without_dependencies_reports_without_import_crash(tmp_path):
    result = subprocess.run([sys.executable, "-S", str(ROOT / "run.py")], input="n\n", capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"})
    assert result.returncode == 1
    assert "PySide6>=6.6" in result.stdout and "edge-tts>=7.3.1,<8" in result.stdout
    assert "ModuleNotFoundError" not in result.stderr


def test_old_python_explains_requirement(monkeypatch, capsys):
    monkeypatch.setattr(launcher.sys, "version_info", (3, 10))
    assert launcher.main() == 1
    assert "Python 3.11" in capsys.readouterr().out


def test_display_command_quotes_powershell_metacharacters():
    assert launcher._powershell_command(["C:/User's Python/python.exe", "edge-tts>=7.3.1,<8"]) == "& 'C:/User''s Python/python.exe' 'edge-tts>=7.3.1,<8'"


def test_real_checkout_copy_without_site_startup_launches_gui(tmp_path):
    import PySide6
    import edge_tts

    checkout = tmp_path / "real checkout"
    checkout.mkdir()
    shutil.copy2(ROOT / "run.py", checkout / "run.py")
    shutil.copy2(ROOT / "pyproject.toml", checkout / "pyproject.toml")
    shutil.copytree(ROOT / "src" / "lingua", checkout / "src" / "lingua", ignore=shutil.ignore_patterns("__pycache__"))
    # Skip site/.pth activation: the installed editable Lingua must not be importable.
    # Expose dependency directories only; no project install/PYTHONPATH in this copy.
    dependency_paths = [str(Path(PySide6.__file__).parent.parent), str(Path(edge_tts.__file__).parent.parent)]
    wrapper = (
        "import sys,runpy,importlib.util; "
        f"sys.path.extend({dependency_paths!r}); "
        "assert importlib.util.find_spec('lingua') is None; "
        "from PySide6 import QtCore; from PySide6.QtWidgets import QApplication; "
        f"settings=QtCore.QSettings({str(tmp_path / 'settings.ini')!r},QtCore.QSettings.IniFormat); "
        "QtCore.QSettings=lambda *a:settings; app=QApplication([]); "
        "QtCore.QTimer.singleShot(200,lambda:(print('ACTUAL_GUI',sys.modules['lingua'].__file__),app.quit())); "
        "runpy.run_path(sys.argv[1],run_name='__main__')"
    )
    result = subprocess.run([sys.executable, "-S", "-c", wrapper, str(checkout / "run.py")], cwd=tmp_path, env={**os.environ, "PYTHONPATH": "", "QT_QPA_PLATFORM": "offscreen", "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ACTUAL_GUI" in result.stdout
    assert str(checkout) in result.stdout
