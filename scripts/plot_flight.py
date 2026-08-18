#!/usr/bin/env python3
"""Summarize avoidance actions and plot the completed QGC flight."""

import collections
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


LOG_PATH = (
    sys.argv[1] if len(sys.argv) > 1 else "/home/hw/logs/avoid_flight.log"
)
OUTPUT = (
    sys.argv[2]
    if len(sys.argv) > 2
    else "/home/hw/logs/flight_trajectory_qgc.png"
)
ROUTE_SOURCE = (
    sys.argv[3]
    if len(sys.argv) > 3
    else "/home/hw/logs/qgc_mission_route.json"
)
ENVIRONMENT = sys.argv[4] if len(sys.argv) > 4 else "AirSim"


def load_waypoints(source):
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
with open(LOG_PATH, encoding="utf-8") as flight_log:
    for line in flight_log:
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 13:
            continue
        ROWS.append(
            (
                float(parts[0]),
                parts[1],
                float(parts[2]),
                float(parts[3]),
                float(parts[4]),
                float(parts[5]),
                float(parts[6]),
                float(parts[7]),
                parts[8],
            )
        )

NAVIGATION = [row for row in ROWS if row[1] == "NAVIGATE"]
print(f"rows={len(ROWS)} navigate={len(NAVIGATION)}")
if not NAVIGATION:
    raise SystemExit("No NAVIGATE rows found in the flight log")

print("--- action counts (NAVIGATE) ---")
for action, count in collections.Counter(row[8] for row in NAVIGATION).most_common():
    print(f"  {action:<10} {count}")

start_time = NAVIGATION[0][0]
print("--- key events ---")
print(
    "  start  : t=%.0fs pos=(%.1f,%.1f)"
    % (0.0, NAVIGATION[0][2], NAVIGATION[0][3])
)
print(
    "  route  : "
    + " -> ".join("(%g,%g)" % waypoint for waypoint in WAYPOINTS)
)
search_start = 0
mission_rows = ROWS[ROWS.index(NAVIGATION[0]):]
for index, waypoint in enumerate(WAYPOINTS):
    remaining = mission_rows[search_start:]
    closest = min(
        remaining,
        key=lambda row: (row[2] - waypoint[0]) ** 2
        + (row[3] - waypoint[1]) ** 2,
    )
    search_start += remaining.index(closest) + 1
    distance = (
        (closest[2] - waypoint[0]) ** 2 + (closest[3] - waypoint[1]) ** 2
    ) ** 0.5
    print(
        "  wp%d (%.0f,%.0f): closest t=%.0fs pos=(%.1f,%.1f) dist=%.1f"
        % (
            index + 1,
            waypoint[0],
            waypoint[1],
            closest[0] - start_time,
            closest[2],
            closest[3],
            distance,
        )
    )
print(
    "  final  : t=%.0fs pos=(%.1f,%.1f)"
    % (
        mission_rows[-1][0] - start_time,
        mission_rows[-1][2],
        mission_rows[-1][3],
    )
)
print("  elapsed: %.0fs" % (mission_rows[-1][0] - start_time))

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
    [row[2] for row in NAVIGATION],
    [row[3] for row in NAVIGATION],
    "-",
    color="#b0bec5",
    linewidth=1.2,
    zorder=1,
)
seen = set()
for row in NAVIGATION:
    action = row[8]
    color, label = COLORS.get(action, ("#90a4ae", action))
    if action not in seen:
        axes.scatter([], [], color=color, s=26, label=label)
        seen.add(action)
    axes.scatter(row[2], row[3], color=color, s=13, zorder=2)

origin = (NAVIGATION[0][2], NAVIGATION[0][3])
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
