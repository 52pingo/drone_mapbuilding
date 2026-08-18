@echo off
title QGC Autonomous Obstacle Avoidance Mission
echo Upload a Takeoff/Waypoint/Land plan in QGroundControl first.
echo This window will stay open until the vehicle lands and disarms.
echo.
wsl -d Ubuntu-22.04 -u hw -- bash /home/hw/tools/run_qgc_mission.sh
echo.
echo Mission runner exited with code %errorlevel%.
pause
