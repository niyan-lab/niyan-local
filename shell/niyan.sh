# shellcheck shell=bash
# Niyan shell hook — sourced after NIYAN_ROOT is set (see `niyan shell init`).
# Mirrors Conda's profile.d pattern: once initialized in ~/.bashrc / ~/.zshrc,
# the `niyan` command is available in every new shell without cd'ing into the repo.

if [ -z "${NIYAN_ROOT:-}" ]; then
  echo "niyan: NIYAN_ROOT is not set; run: niyan shell init" >&2
  return 1 2>/dev/null || exit 1
fi

export NIYAN_HOME="${NIYAN_HOME:-$NIYAN_ROOT}"

# Unix venv uses bin/; Windows Python under Git Bash uses Scripts/
if [ -d "$NIYAN_ROOT/.venv/bin" ]; then
  _niyan_bin="$NIYAN_ROOT/.venv/bin"
elif [ -d "$NIYAN_ROOT/.venv/Scripts" ]; then
  _niyan_bin="$NIYAN_ROOT/.venv/Scripts"
else
  echo "niyan: missing $NIYAN_ROOT/.venv/bin (or Scripts) — re-run ./install.sh or .\\install.ps1" >&2
  unset _niyan_bin
  return 1 2>/dev/null || exit 1
fi

case ":${PATH}:" in
  *":${_niyan_bin}:"*) ;;
  *) PATH="${_niyan_bin}:${PATH}"; export PATH ;;
esac
unset _niyan_bin
