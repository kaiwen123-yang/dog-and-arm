#!/usr/bin/env bash
# Run project commands without inheriting Conda/ROS Python and library paths.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ "$#" -eq 0 ]]; then
    printf '%s\n' 'Usage: bash scripts/project_env.sh COMMAND [ARGUMENTS...]' >&2
    exit 2
fi

project_environment=(
    "HOME=${HOME}"
    "PATH=${project_root}/.venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    "LANG=${LANG:-C.UTF-8}"
    "PYTHONNOUSERSITE=1"
)
# Preserve only relevant desktop, connection and renderer settings. Values are
# forwarded unchanged, never printed. PYTHONPATH, PYTHONHOME, CONDA_* and
# LD_LIBRARY_PATH are deliberately not forwarded. Run ROS tools separately.
for variable_name in \
    USER LOGNAME SHELL TERM COLORTERM TMPDIR LC_ALL LC_CTYPE \
    DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_RUNTIME_DIR XDG_SESSION_TYPE \
    DBUS_SESSION_BUS_ADDRESS QT_QPA_PLATFORM QT_X11_NO_MITSHM \
    SSH_AUTH_SOCK \
    http_proxy https_proxy all_proxy no_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY \
    SSL_CERT_FILE SSL_CERT_DIR REQUESTS_CA_BUNDLE CURL_CA_BUNDLE \
    PIP_INDEX_URL PIP_EXTRA_INDEX_URL PIP_TRUSTED_HOST PIP_CERT \
    MUJOCO_GL PYOPENGL_PLATFORM MUJOCO_EGL_DEVICE_ID EGL_DEVICE_ID \
    CUDA_VISIBLE_DEVICES NVIDIA_VISIBLE_DEVICES; do
    if [[ -v "$variable_name" ]]; then
        project_environment+=("${variable_name}=${!variable_name}")
    fi
done

cd -- "$project_root"
exec env -i "${project_environment[@]}" "$@"
