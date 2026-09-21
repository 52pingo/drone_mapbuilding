#!/usr/bin/env python3
"""Plot the finished QGC flight, colored by what the avoidance logic did."""

import collections
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


LOG_PATH = sys.argv[1] if len(sys.argv) > 1 else "/home/hw/logs/avoid_flight.log"
OUTPUT = (
    sys.argv[2] if len(sys.argv) > 2 else "/home/hw/logs/flight_trajectory_qgc.png"
)
ROUTE_SOURCE = (
    sys.argv[3] if len(sys.argv) > 3 else "/home/hw/logs/qgc_mission_route.json"
)
ENVIRONMENT = sys.argv[4] if len(sys.argv) > 4 else "AirSim"


# 日志列索引: t action x y z vx vy vz decision ...
COL_TIME = 0
COL_ACTION = 1
COL_NORTH = 2
COL_EAST = 3
COL_ALT = 4
COL_VX = 5
COL_VY = 6
COL_VZ = 7
COL_DECISION = 8
MIN_COLUMNS = COL_DECISION + 1


def _parse_row(parts):
    """把一行日志字段解析成 tuple；字段不够或数字坏掉时返回 None。"""
    if len(parts) < MIN_COLUMNS:
        return None
    try:
        return (
            float(parts[COL_TIME]),
            parts[COL_ACTION],
            float(parts[COL_NORTH]),
            float(parts[COL_EAST]),
            float(parts[COL_ALT]),
            float(parts[COL_VX]),
            float(parts[COL_VY]),
            float(parts[COL_VZ]),
            parts[COL_DECISION],
        )
    except ValueError:
        return None


def load_waypoints(source):
    # 要么是 QGC 导出的 json，要么是 "n,e;n,e;..." 这种手写串
    if source.lower().endswith(".json"):
        with open(source, encoding="utf-8") as route_file:
            route = json.load(route_file)["route"]
        return [(float(point["north_m"]), float(point["east_m"])) for point in route]
    return [
        (float(point.split(",")[0]), float(point.split(",")[1]))
        for point in source.split(";")
    ]


WAYPOINTS = load_waypoints(ROUTE_SOURCE)

ROWS = []
with open(LOG_PATH, encoding="utf-8-sig") as flight_log:
    for line in flight_log:
        if line.startswith("#"):
            continue
        row = _parse_row(line.split())
        if row is not None:
            ROWS.append(row)

NAVIGATION = [row for row in ROWS if row[COL_ACTION] == "NAVIGATE"]
print(f"rows={len(ROWS)} navigate={len(NAVIGATION)}")
if not NAVIGATION:
    raise SystemExit("No NAVIGATE rows found in the flight log")

print("--- action counts (NAVIGATE) ---")
for action, count in collections.Counter(
    row[COL_DECISION] for row in NAVIGATION
).most_common():
    print(f"  {action:<10} {count}")

start_time = NAVIGATION[0][COL_TIME]
print("--- key events ---")
print(
    "  start  : t=%.0fs pos=(%.1f,%.1f)"
    % (0.0, NAVIGATION[0][COL_NORTH], NAVIGATION[0][COL_EAST])
)
print("  route  : " + " -> ".join("(%g,%g)" % wp for wp in WAYPOINTS))

# 对每个航点找时间上最近的经过点；搜索指针只往前走，避免来回匹配
search_start = 0
mission_rows = ROWS[ROWS.index(NAVIGATION[0]):]
for index, waypoint in enumerate(WAYPOINTS):
    remaining = mission_rows[search_start:]
    closest = min(
        remaining,
        key=lambda row: (row[COL_NORTH] - waypoint[0]) ** 2
        + (row[COL_EAST] - waypoint[1]) ** 2,
    )
    search_start += remaining.index(closest) + 1
    distance = (
        (closest[COL_NORTH] - waypoint[0]) ** 2
        + (closest[COL_EAST] - waypoint[1]) ** 2
    ) ** 0.5
    print(
        "  wp%d (%.0f,%.0f): closest t=%.0fs pos=(%.1f,%.1f) dist=%.1f"
        % (
            index + 1,
            waypoint[0],
            waypoint[1],
            closest[COL_TIME] - start_time,
            closest[COL_NORTH],
            closest[COL_EAST],
            distance,
        )
    )
print(
    "  final  : t=%.0fs pos=(%.1f,%.1f)"
    % (
        mission_rows[-1][COL_TIME] - start_time,
        mission_rows[-1][COL_NORTH],
        mission_rows[-1][COL_EAST],
    )
)
print("  elapsed: %.0fs" % (mission_rows[-1][COL_TIME] - start_time))

# 每种 action 一个颜色，图例里给个能看懂的名字
COLORS = {
    "go": ("#2e7d32", "forward"),
    "slow": ("#ffb300", "slow"),
    "near": ("#ff8f00", "near"),
    "backup": ("#d32f2f", "backup"),
    "avoidL": ("#1976d2", "avoid left"),
    "avoidR": ("#7b1fa2", "avoid right"),
    "recover": ("#e91e63", "recover"),
    "boxed": ("#000000", "boxed"),
    "arrived": ("#00897b", "arrived"),
    "rearm": ("#9e9e9e", "rearm"),
    "TIMEOUT": ("#616161", "timeout"),
}

figure, axes = plt.subplots(figsize=(9, 8))
axes.plot(
    [row[COL_NORTH] for row in NAVIGATION],
    [row[COL_EAST] for row in NAVIGATION],
    "-",
    color="#b0bec5",
    linewidth=1.2,
    zorder=1,
)

# 按 action 分组：每个 action 只调一次 scatter，artist 数与 action 种类同阶
grouped = collections.OrderedDict()
for row in NAVIGATION:
    grouped.setdefault(row[COL_DECISION], []).append(row)
for action, rows in grouped.items():
    color, label = COLORS.get(action, ("#90a4ae", action))
    # 空 scatter 只用于图例，保持原 s=26 的图例标记大小
    axes.scatter([], [], color=color, s=26, label=label)
    axes.scatter(
        [row[COL_NORTH] for row in rows],
        [row[COL_EAST] for row in rows],
        color=color,
        s=13,
        zorder=2,
    )

origin = (NAVIGATION[0][COL_NORTH], NAVIGATION[0][COL_EAST])
route_points = [origin, *WAYPOINTS]
axes.plot(
    [waypoint[0] for waypoint in route_points],
    [waypoint[1] for waypoint in route_points],
    "--",
    color="#78909c",
    linewidth=0.9,
    alpha=0.6,
    label="QGC route",
    zorder=1,
)
axes.scatter(
    origin[0],
    origin[1],
    marker="*",
    s=200,
    color="#000000",
    label="mission origin",
    zorder=7,
)
for index, waypoint in enumerate(WAYPOINTS):
    axes.scatter(
        waypoint[0],
        waypoint[1],
        marker="P",
        s=200,
        color="#c62828",
        zorder=5,
    )
    axes.annotate(
        f"wp{index + 1}",
        xy=waypoint,
        xytext=(waypoint[0] + 0.8, waypoint[1] + 0.8),
        fontsize=8,
        color="#37474f",
    )
axes.set_xlabel("x (m, North)")
axes.set_ylabel("y (m, East)")
axes.set_title(
    "QGC autonomous obstacle-avoidance flight\n"
    f"action-colored trajectory, {ENVIRONMENT} environment"
)
axes.legend(loc="upper left", fontsize=8, ncol=2)
axes.grid(alpha=0.3)
axes.set_aspect("equal", adjustable="box")
plt.tight_layout()
plt.savefig(OUTPUT, dpi=110)
print(f"saved -> {OUTPUT}")
