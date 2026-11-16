#!/usr/bin/env bash
# Load an existing ROS installation/overlay in a clean environment.
# This wrapper does not install software or start any hardware by itself.
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
jointcheck_ros_setup=/opt/ros/humble/setup.bash
jointcheck_overlays=()
while [[ "$#" -gt 0 ]]; do
    case "$1" in
        --ros-setup) jointcheck_ros_setup="$2"; shift 2 ;;
        --overlay) jointcheck_overlays+=("$2"); shift 2 ;;
        --) shift; break ;;
        -h|--help)
            printf '%s\n' 'Usage: bash scripts/hardware_env.sh [--ros-setup FILE] [--overlay FILE] -- COMMAND [ARGS...]'
            exit 0 ;;
        *) break ;;
    esac
done
if [[ "$#" -eq 0 ]]; then
    printf '%s\n' 'Provide a ROS command after --. Use --help for usage.' >&2
    exit 2
fi
for jointcheck_setup in "$jointcheck_ros_setup" "${jointcheck_overlays[@]}"; do
    if [[ ! -f "$jointcheck_setup" ]]; then
        printf 'Existing ROS setup file not found: %s\n' "$jointcheck_setup" >&2
        exit 1
    fi
done

jointcheck_ros_environment=()
for variable_name in ROS_DOMAIN_ID ROS_LOCALHOST_ONLY RMW_IMPLEMENTATION \
    CYCLONEDDS_URI FASTRTPS_DEFAULT_PROFILES_FILE FASTDDS_DEFAULT_PROFILES_FILE \
    ROS_DISCOVERY_SERVER; do
    if [[ -v "$variable_name" ]]; then
        jointcheck_ros_environment+=("${variable_name}=${!variable_name}")
    fi
done

# project_env keeps display/proxy settings. Override its venv-prefixed PATH
# before sourcing ROS so ROS uses the system Python it was built for.
# Do not enable nounset inside the ROS shell: existing setup files may read
# unset variables as part of their normal environment setup.
exec bash "${project_root}/scripts/project_env.sh" env \
    "PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    "${jointcheck_ros_environment[@]}" /bin/bash --noprofile --norc -c '
        set -eo pipefail
        jointcheck_base_setup=$1
        jointcheck_overlay_count=$2
        shift 2
        source "$jointcheck_base_setup"
        for ((jointcheck_index=0; jointcheck_index<jointcheck_overlay_count; jointcheck_index++)); do
            source "$1"
            shift
        done
        exec "$@"
    ' hardware_env "$jointcheck_ros_setup" "${#jointcheck_overlays[@]}" "${jointcheck_overlays[@]}" "$@"
