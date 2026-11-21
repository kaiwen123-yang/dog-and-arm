#!/usr/bin/env bash
# Launch B0 with isolated Python/native search paths and optional desktop variables.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ $# -eq 0 ]]; then
    echo 'Usage: bash scripts/b0/env.sh COMMAND [ARGUMENTS...]' >&2
    exit 2
fi
cd "$root"
if [[ ! -x .venv-b0/bin/python ]]; then
    echo 'Create the B0 environment with scripts/b0/setup_env.sh first.' >&2
    exit 1
fi
export PATH="$root/.venv-b0/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH CONDA_PREFIX
export VIRTUAL_ENV="$root/.venv-b0" PYTHONNOUSERSITE=1 PYTHONPATH="$root"
exec "$@"
