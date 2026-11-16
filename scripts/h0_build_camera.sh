#!/usr/bin/env bash
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$root/hardware/camera_ws/src/ros2_astra_camera"
revision=f7e71d9ce806e788cb48d8580aac2c778fba4214
if [[ ! -d "$source_dir/.git" ]]; then
    mkdir -p "$(dirname "$source_dir")"
    git clone https://github.com/orbbec/ros2_astra_camera.git "$source_dir"
    git -C "$source_dir" checkout --detach "$revision"
fi
[[ $(git -C "$source_dir" rev-parse HEAD) == "$revision" ]] || {
    echo 'Camera source revision differs; inspect before building.' >&2; exit 1;
}
if [[ ! -f /usr/include/nlohmann/json.hpp && ! -f "$root/hardware/deps/usr/include/nlohmann/json.hpp" ]]; then
    mkdir -p "$root/hardware/deps"
    (cd "$root/hardware/deps"
     apt-get download nlohmann-json3-dev=3.10.5-2
     dpkg-deb -x nlohmann-json3-dev_3.10.5-2_all.deb .)
fi
exec bash "$root/scripts/hardware_env.sh" -- bash -c '
    export CPLUS_INCLUDE_PATH="$PWD/hardware/deps/usr/include"
    cd hardware/camera_ws
    export CMAKE_BUILD_PARALLEL_LEVEL=4
    exec colcon build --executor sequential --cmake-args \
        -DBUILD_TESTING=OFF -DPython3_EXECUTABLE=/usr/bin/python3
'
