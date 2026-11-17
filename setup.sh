#!/usr/bin/env bash
# Run from any directory; installs into this checkout's .venv.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

if [[ "${1:-}" == "--help" ]]; then
    echo 'Usage: bash setup.sh [--conda]'
    echo 'Default: requires Python 3.14+ with venv and pip; creates .venv.'
    echo 'Conda: requires conda; creates the environment from environment.yml.'
    exit 0
fi
if [[ "${1:-}" == "--conda" && "$#" == 1 ]]; then
    command -v conda >/dev/null || { echo 'Install Conda first.' >&2; exit 1; }
    conda env create -f environment.yml
    echo 'Activate with: conda activate shacl-py'
    echo 'Then run: shacl-py serve examples'
    exit 0
fi
if [[ "$#" != 0 ]]; then
    echo 'Usage: bash setup.sh [--conda]' >&2
    exit 1
fi

python_bin=''
for candidate in python3.14 python3 python; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 14))' 2>/dev/null; then
        python_bin="$candidate"
        break
    fi
done
if [[ -z "$python_bin" ]]; then
    echo 'Install Python 3.14 or later with pip and venv, or use bash setup.sh --conda.' >&2
    exit 1
fi
if [[ -e .venv ]]; then
    if [[ ! -x .venv/bin/python ]] || ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 14))'; then
        echo 'Existing .venv is incompatible. Move it aside before running setup again.' >&2
        exit 1
    fi
else
    "$python_bin" -m venv .venv
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    .venv/bin/python -m ensurepip --upgrade
fi
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/shacl-py --help
.venv/bin/shacl-py validate examples
echo "Activate with: source '$PWD/.venv/bin/activate'"
echo 'Then run: shacl-py serve examples'
