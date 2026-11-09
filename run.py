"""Run this checkout without installing the project; install dependencies only on consent."""
import importlib.util
from pathlib import Path
import re
import site
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
AFTER_INSTALL = "--lingua-after-install"


def _version(text):
    if not re.fullmatch(r"\d+(?:\.\d+)*", text):
        raise ValueError(f"無法辨識版本 {text!r}（需要正式發行版）")
    parts = [int(part) for part in text.split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _powershell_command(arguments):
    return "& " + " ".join("'" + argument.replace("'", "''") + "'" for argument in arguments)


def dependency_problems(requirements):
    from importlib import metadata

    problems = []
    for requirement in requirements:
        match = re.fullmatch(r"([A-Za-z0-9_-]+)((?:>=|<)\d+(?:\.\d+)*(?:,(?:>=|<)\d+(?:\.\d+)*)*)", requirement)
        if not match:
            raise ValueError(f"啟動器不支援此依賴條件：{requirement}")
        name, bounds = match.groups()
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            problems.append((requirement, "尚未安裝"))
            continue
        try:
            current = _version(installed)
            matches = all(
                current >= _version(bound[2:]) if bound.startswith(">=") else current < _version(bound[1:])
                for bound in bounds.rstrip(",").split(",")
            )
        except ValueError:
            matches = False
        if not matches:
            problems.append((requirement, f"目前版本 {installed} 不符合"))
    return problems


def install_dependencies(problems, after_install=False):
    print(f"使用的 Python：{sys.executable}（{sys.version.split()[0]}）")
    for requirement, reason in problems:
        print(f"  {requirement}：{reason}")
    if after_install:
        print("安裝後仍無法找到符合版本的依賴，已停止，不會反覆安裝。請檢查上方 Python 與 pip 輸出。")
        return 1
    virtualenv = sys.prefix != sys.base_prefix
    if not virtualenv and not site.ENABLE_USER_SITE:
        print("此 Python 已停用使用者套件目錄；請以一般 py run.py 啟動，或選用虛擬環境，不會改動系統設定。")
        return 1
    command = [sys.executable, "-m", "pip", "install"]
    if not virtualenv:
        command.append("--user")
    command.extend(requirement for requirement, _ in problems)
    target = sys.prefix if virtualenv else site.getusersitepackages()
    print(f"安裝目標：{target}（{'目前虛擬環境' if virtualenv else '目前 Python 的使用者套件目錄'}）")
    print("只安裝必要依賴，不安裝 Lingua 專案；需要網路或可用的本機 pip 快取／來源。")
    print("安裝指令（PowerShell）：" + _powershell_command(command))
    if importlib.util.find_spec("pip") is None:
        print("這個 Python 沒有 pip。請先自行安裝 pip，再重跑 py run.py；不會自動下載安裝器。")
        bootstrap = [sys.executable, "-m", "ensurepip"] + ([] if virtualenv else ["--user"])
        print("若此 Python 提供 ensurepip，可自行執行：" + _powershell_command(bootstrap))
        return 1
    try:
        answer = input("是否執行上述安裝？[y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt, OSError):
        answer = ""
    if answer not in {"y", "yes"}:
        print("未安裝。準備好依賴後，再執行 py run.py。多 Python 版本可使用 py -3.14 run.py 選定版本。")
        return 1
    try:
        completed = subprocess.run(command, check=False)
        if completed.returncode:
            print(f"安裝失敗（結束碼 {completed.returncode}），未啟動 Lingua。請檢查網路、權限及上方 pip 錯誤後重試。")
            return 1
        print("安裝指令完成，使用同一個 Python 重新檢查並啟動。")
        return subprocess.run([sys.executable, str(ROOT / "run.py"), AFTER_INSTALL, *sys.argv[1:]], check=False).returncode
    except OSError as error:
        print(f"無法執行安裝／重新啟動：{error}")
        return 1


def main():
    if sys.version_info < (3, 11):
        print(f"Lingua 需要 Python 3.11 或更新版本，目前為 {sys.version.split()[0]}。")
        print("請先安裝合適版本；多版本可用 py --list 查看，再執行例如 py -3.14 run.py。")
        return 1
    import tomllib

    after_install = AFTER_INSTALL in sys.argv
    if after_install:
        sys.argv.remove(AFTER_INSTALL)
    try:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        problems = dependency_problems(project["dependencies"])
    except (OSError, ValueError, KeyError) as error:
        print(f"無法讀取此 checkout 的啟動設定：{error}")
        return 1
    if problems:
        return install_dependencies(problems, after_install)
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import lingua
        if Path(lingua.__file__).resolve() != ROOT / "src" / "lingua" / "__init__.py":
            raise ImportError("載入了不同位置的 lingua，請以新的 Python 程序執行本 checkout 的 run.py")
        from lingua.app import main as run_app
    except (ImportError, OSError) as error:
        print(f"依賴已安裝，但載入失敗：{error}\nPython：{sys.executable}\n請確認套件及其原生元件可用。")
        return 1
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
