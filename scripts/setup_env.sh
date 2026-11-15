#!/usr/bin/env bash
# Install only into this project's .venv. No sudo or shell-profile edits.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
project_runner="${project_root}/scripts/project_env.sh"

bash "$project_runner" /usr/bin/python3 scripts/init_workspace.py
if [[ ! -d "${project_root}/.venv" ]]; then
    if ! bash "$project_runner" /usr/bin/python3 -m venv "${project_root}/.venv"; then
        printf '%s\n' \
            'Could not create .venv; read the actual Python error above.' \
            'On Ubuntu, a missing ensurepip/venv module may require python3-venv.' \
            'No existing ROS, Conda, CUDA or system Python packages were changed.' >&2
        exit 1
    fi
fi

if [[ ! -x "${project_root}/.venv/bin/python" ]]; then
    printf '%s\n' '.venv exists but has no executable Python. Inspect it before replacing anything.' >&2
    exit 1
fi

bash "$project_runner" "${project_root}/.venv/bin/python" -m pip install -r requirements.txt
bash "$project_runner" "${project_root}/.venv/bin/python" -m pip freeze > "${project_root}/reports/requirements_resolved.txt"
bash "$project_runner" "${project_root}/.venv/bin/python" -c \
    'import sys, mujoco; print("Python:", sys.version.split()[0]); print("MuJoCo:", mujoco.__version__)'
printf '%s\n' 'Environment ready. Next: bash scripts/project_env.sh .venv/bin/python scripts/fetch_sources.py'
