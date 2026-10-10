"""Conda-style shell initialization for the Niyan CLI (bash/zsh/fish/PowerShell)."""

from __future__ import annotations

import os
import platform
import re
from pathlib import Path
from typing import Optional, Tuple


BEGIN = "# >>> niyan initialize >>>"
END = "# <<< niyan initialize <<<"

LEGACY_BEGIN = "# >>> novus initialize >>>"
LEGACY_END = "# <<< novus initialize <<<"

BLOCK_RE = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
    re.DOTALL,
)
LEGACY_BLOCK_RE = re.compile(
    re.escape(LEGACY_BEGIN) + r".*?" + re.escape(LEGACY_END) + r"\n?",
    re.DOTALL,
)


def venv_scripts_dir(repo_root: Path) -> Path:
    """Return the venv executables dir (Scripts on Windows, bin elsewhere)."""
    scripts = repo_root / ".venv" / "Scripts"
    if scripts.exists() or platform.system().lower() == "windows":
        return scripts
    return repo_root / ".venv" / "bin"


def detect_shell(explicit: Optional[str] = None) -> str:
    if explicit:
        name = explicit.lower().strip()
        if name in {"pwsh", "powershell", "ps"}:
            return "powershell"
        return name
    # Windows defaults to PowerShell when $SHELL is unset / not useful
    if platform.system().lower() == "windows":
        return "powershell"
    shell = Path(os.environ.get("SHELL", "/bin/zsh")).name.lower()
    if "bash" in shell:
        return "bash"
    if "zsh" in shell:
        return "zsh"
    if "fish" in shell:
        return "fish"
    return "zsh"


def rc_path_for(shell: str, home: Optional[Path] = None) -> Path:
    home = home or Path.home()
    if shell == "bash":
        bashrc = home / ".bashrc"
        bash_profile = home / ".bash_profile"
        if bashrc.exists() or not bash_profile.exists():
            return bashrc
        return bash_profile
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "fish":
        return home / ".config" / "fish" / "config.fish"
    if shell == "powershell":
        # CurrentUserCurrentHost profile (same idea as conda init powershell)
        docs = Path(os.environ.get("USERPROFILE", str(home))) / "Documents"
        # Windows PowerShell 5.x vs PowerShell 7+
        for candidate in (
            docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1",
            docs / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1",
        ):
            if candidate.exists():
                return candidate
        # Prefer PowerShell 7 path when creating new
        return docs / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    raise ValueError(f"unsupported shell: {shell}")


def build_block(repo_root: Path, shell: str) -> str:
    root = str(repo_root.resolve())
    if shell == "powershell":
        hook = repo_root / "shell" / "niyan.ps1"
        # Escape single quotes for PowerShell single-quoted strings
        root_ps = root.replace("'", "''")
        hook_ps = str(hook.resolve()).replace("'", "''")
        return (
            f"{BEGIN}\n"
            f"$env:NIYAN_ROOT = '{root_ps}'\n"
            f"$env:NIYAN_HOME = $env:NIYAN_ROOT\n"
            f". '{hook_ps}'\n"
            f"{END}\n"
        )
    if shell == "fish":
        return (
            f"{BEGIN}\n"
            f"set -gx NIYAN_ROOT '{root}'\n"
            f"set -gx NIYAN_HOME $NIYAN_ROOT\n"
            f"if test -d $NIYAN_ROOT/.venv/bin\n"
            f"    set -gx PATH $NIYAN_ROOT/.venv/bin $PATH\n"
            f"else if test -d $NIYAN_ROOT/.venv/Scripts\n"
            f"    set -gx PATH $NIYAN_ROOT/.venv/Scripts $PATH\n"
            f"end\n"
            f"{END}\n"
        )
    # bash / zsh
    hook = repo_root / "shell" / "niyan.sh"
    return (
        f"{BEGIN}\n"
        f'export NIYAN_ROOT="{root}"\n'
        f'export NIYAN_HOME="$NIYAN_ROOT"\n'
        f'. "{hook}"\n'
        f"{END}\n"
    )


def apply_init(rc_file: Path, block: str) -> Tuple[str, Path]:
    """Install or replace the niyan initialize block. Returns (action, path)."""
    rc_file.parent.mkdir(parents=True, exist_ok=True)
    existing = rc_file.read_text(encoding="utf-8") if rc_file.exists() else ""
    if BEGIN in existing:
        updated = BLOCK_RE.sub(block, existing)
        if not updated.endswith("\n") and block:
            updated += "\n"
        rc_file.write_text(updated, encoding="utf-8")
        return "updated", rc_file
    separator = "" if (not existing or existing.endswith("\n")) else "\n"
    rc_file.write_text(existing + separator + "\n" + block, encoding="utf-8")
    return "installed", rc_file


def remove_init(rc_file: Path) -> bool:
    if not rc_file.exists():
        return False
    existing = rc_file.read_text(encoding="utf-8")
    if BEGIN not in existing:
        return False
    updated = BLOCK_RE.sub("", existing)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    rc_file.write_text(updated, encoding="utf-8")
    return True


def remove_legacy_init(rc_file: Path) -> bool:
    """Remove pre-rename Novus shell block from rc file."""
    if not rc_file.exists():
        return False
    existing = rc_file.read_text(encoding="utf-8")
    if LEGACY_BEGIN not in existing:
        return False
    updated = LEGACY_BLOCK_RE.sub("", existing)
    updated = re.sub(r"\n{3,}", "\n\n", updated)
    rc_file.write_text(updated, encoding="utf-8")
    return True


def init_shell(repo_root: Path, shell: Optional[str] = None, reverse: bool = False) -> Tuple[str, Path]:
    sh = detect_shell(shell)
    rc = rc_path_for(sh)
    if reverse:
        removed = remove_init(rc)
        return ("removed" if removed else "absent"), rc
    remove_legacy_init(rc)
    block = build_block(repo_root, sh)
    return apply_init(rc, block)
