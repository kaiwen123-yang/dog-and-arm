#!/usr/bin/env bash
# Same DDS transport for the H0 camera and its subscribers; no hardware startup.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export ROS_DOMAIN_ID=88 ROS_LOCALHOST_ONLY=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$root/config/h0_fastdds.xml"
exec bash "$root/scripts/hardware_env.sh" --overlay "$root/hardware/camera_ws/install/setup.bash" -- "$@"
