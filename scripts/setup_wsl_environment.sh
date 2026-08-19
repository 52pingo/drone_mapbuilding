#!/usr/bin/env bash
# Idempotent ROS2 Humble, PX4 v1.15.2, XRCE-DDS, and workspace setup.
set -euo pipefail

MODE="${1:-check}"
TARGET_USER="${2:-hw}"
ROS_WORKSPACE="${3:-/home/$TARGET_USER/hw-ros2/ros2}"
PX4_DIR="${4:-/home/$TARGET_USER/px4v1.15.2}"
XRCE_BIN="${5:-/home/$TARGET_USER/Micro-XRCE-DDS-Agent/build/MicroXRCEAgent}"
PROJECT_ROOT="${6:-}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"

emit() {
    local component="$1" status="$2" detail="$3"
    detail="${detail//\\/\\\\}"; detail="${detail//\"/\\\"}"
    printf 'GUI_SETUP {"component":"%s","status":"%s","detail":"%s"}\n' \
        "$component" "$status" "$detail"
}

check_all() {
    if [ -r /opt/ros/humble/setup.bash ]; then emit ros2 pass 'ROS2 Humble ready'; else emit ros2 fail 'ROS2 Humble missing'; fi
    if [ -x "$PX4_DIR/build/px4_sitl_default/bin/px4" ]; then emit px4 pass "$PX4_DIR"; else emit px4 fail "PX4 SITL missing: $PX4_DIR"; fi
    if [ -x "$XRCE_BIN" ]; then emit xrce pass "$XRCE_BIN"; else emit xrce fail "Micro XRCE-DDS missing: $XRCE_BIN"; fi
    if [ -r "$ROS_WORKSPACE/install/setup.bash" ]; then emit ros_workspace pass "$ROS_WORKSPACE"; else emit ros_workspace fail "ROS workspace not built: $ROS_WORKSPACE"; fi
}

if [ "$MODE" = check ]; then
    check_all
    exit 0
fi
if [ "$(id -u)" -ne 0 ]; then
    emit installer fail 'WSL setup must run as root'
    exit 2
fi
if [ -z "$TARGET_HOME" ]; then
    emit wsl_user running "Creating WSL user: $TARGET_USER"
    useradd --create-home --shell /bin/bash "$TARGET_USER"
    usermod -aG sudo "$TARGET_USER"
    printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$TARGET_USER" > "/etc/sudoers.d/90-$TARGET_USER-drone-setup"
    chmod 0440 "/etc/sudoers.d/90-$TARGET_USER-drone-setup"
    TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
    emit wsl_user pass "Created WSL user: $TARGET_USER"
fi

export DEBIAN_FRONTEND=noninteractive
emit apt running 'Installing Ubuntu and ROS2 prerequisites'
apt-get update
apt-get install -y locales curl gnupg lsb-release software-properties-common git cmake build-essential python3-pip python3-rosdep python3-colcon-common-extensions rsync
locale-gen en_US en_US.UTF-8
update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8
add-apt-repository universe -y
if [ ! -f /usr/share/keyrings/ros-archive-keyring.gpg ]; then
    curl -sSL https://raw.githubusercontent.com/ros/rosdistro/master/ros.key \
        -o /usr/share/keyrings/ros-archive-keyring.gpg
fi
arch="$(dpkg --print-architecture)"; codename="$(. /etc/os-release && echo "$UBUNTU_CODENAME")"
printf 'deb [arch=%s signed-by=/usr/share/keyrings/ros-archive-keyring.gpg] http://packages.ros.org/ros2/ubuntu %s main\n' "$arch" "$codename" \
    > /etc/apt/sources.list.d/ros2.list
apt-get update
apt-get install -y ros-humble-desktop ros-dev-tools ros-humble-depth-image-proc ros-humble-octomap-server ros-humble-topic-tools
emit ros2 pass 'ROS2 Humble installed'

if [ ! -d "$PX4_DIR/.git" ]; then
    mkdir -p "$(dirname "$PX4_DIR")"
    git clone --branch v1.15.2 --recursive https://github.com/PX4/PX4-Autopilot.git "$PX4_DIR"
fi
git -C "$PX4_DIR" submodule update --init --recursive
bash "$PX4_DIR/Tools/setup/ubuntu.sh" --no-nuttx --no-sim-tools
chown -R "$TARGET_USER":"$TARGET_USER" "$PX4_DIR"
runuser -u "$TARGET_USER" -- bash -lc "cd '$PX4_DIR' && make px4_sitl_default none_iris"
emit px4 pass 'PX4 v1.15.2 none_iris built'

xrce_root="$(dirname "$(dirname "$XRCE_BIN")")"
if [ ! -d "$xrce_root/.git" ]; then
    git clone --branch 2.4.2 --depth 1 https://github.com/eProsima/Micro-XRCE-DDS-Agent.git "$xrce_root"
fi
cmake -S "$xrce_root" -B "$xrce_root/build"
cmake --build "$xrce_root/build" --parallel "$(nproc)"
chown -R "$TARGET_USER":"$TARGET_USER" "$xrce_root"
emit xrce pass 'Micro XRCE-DDS Agent 2.4.2 built'

airsim_root="$TARGET_HOME/AirSim"
if [ ! -d "$airsim_root/.git" ]; then
    runuser -u "$TARGET_USER" -- git clone --branch v1.8.1 --depth 1 https://github.com/microsoft/AirSim.git "$airsim_root"
fi
mkdir -p "$ROS_WORKSPACE/src"
ln -sfn "$airsim_root/ros2/src/airsim_interfaces" "$ROS_WORKSPACE/src/airsim_interfaces"
ln -sfn "$airsim_root/ros2/src/airsim_ros_pkgs" "$ROS_WORKSPACE/src/airsim_ros_pkgs"
if [ ! -d "$ROS_WORKSPACE/src/px4_msgs/.git" ]; then
    runuser -u "$TARGET_USER" -- git clone --branch release/1.15 --depth 1 https://github.com/PX4/px4_msgs.git "$ROS_WORKSPACE/src/px4_msgs"
fi
if [ -d "$PROJECT_ROOT/ros2_ws/src/hw_insight" ]; then
    mkdir -p "$ROS_WORKSPACE/src/hw_insight"
    rsync -a --delete "$PROJECT_ROOT/ros2_ws/src/hw_insight/" "$ROS_WORKSPACE/src/hw_insight/"
else
    emit ros_workspace fail "Project ROS source missing: $PROJECT_ROOT/ros2_ws/src/hw_insight"
    exit 3
fi
chown -R "$TARGET_USER":"$TARGET_USER" "$ROS_WORKSPACE" "$airsim_root"
rosdep init 2>/dev/null || true
runuser -u "$TARGET_USER" -- rosdep update
runuser -u "$TARGET_USER" -- bash -lc "source /opt/ros/humble/setup.bash && cd '$ROS_WORKSPACE' && rosdep install --from-paths src --ignore-src -r -y && colcon build --symlink-install"
emit ros_workspace pass 'AirSim ROS2, px4_msgs, and hw_insight built'
check_all
