#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec bash "$root/scripts/h0_ros_env.sh" \
    ros2 launch astra_camera dabai_dc1.launch.xml \
    camera_name:=wrist_camera uvc_product_id:=0x0557 \
    enable_ir:=false enable_point_cloud:=false enable_colored_point_cloud:=false \
    depth_registration:=false color_depth_synchronization:=false depth_scale:=1 \
    color_width:=640 color_height:=480 color_fps:=30 \
    depth_width:=640 depth_height:=400 depth_fps:=30 "$@"
