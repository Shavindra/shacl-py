#!/usr/bin/env bash
# Install into the currently active Conda or Python virtual environment.
set -euo pipefail

if [[ "${1:-}" == "--help" && "$#" == 1 ]]; then
    echo 'Usage: bash setup.sh'
    echo 'Activate a Conda or Python virtual environment with Python 3.14+ first.'
    echo 'Requires pip, Git and internet access. Creates no environment.'
    exit 0
fi
if [[ "$#" != 0 ]]; then
    echo 'Usage: bash setup.sh' >&2
    exit 1
fi

# Use the active environment interpreter, never a separately located Python.
if command -v python >/dev/null; then
    python_bin=python
elif command -v python3 >/dev/null; then
    python_bin=python3
else
    echo 'Activate an environment containing Python 3.14 or later first.' >&2
    exit 1
fi
"$python_bin" - <<'PY'
import os
import sys
from pathlib import Path

prefix = Path(sys.prefix).resolve()
conda = os.environ.get('CONDA_PREFIX')
virtual = os.environ.get('VIRTUAL_ENV')
active = any(value and Path(value).resolve() == prefix for value in (conda, virtual))
if not active:
    sys.exit('No matching active Conda/virtual environment. Activate one first; nothing was installed.')
if sys.version_info < (3, 14):
    sys.exit('The active environment needs Python 3.14 or later. Nothing was installed.')
print(f'Installing into {prefix} using Python {sys.version.split()[0]}', flush=True)
PY
command -v git >/dev/null || { echo 'Git is required. On macOS, install the Command Line Tools with xcode-select --install.' >&2; exit 1; }
git --version >/dev/null
"$python_bin" -m pip --version >/dev/null || { echo 'Install pip in the active environment first.' >&2; exit 1; }
"$python_bin" -m pip install --upgrade 'git+https://github.com/Shavindra/shacl-py.git'
"$python_bin" - <<'PY'
from shacl_py.cli import main
raise SystemExit(main(['--help']))
PY
echo 'Installed. From your project, run shacl-py setup and then shacl-py serve .'
