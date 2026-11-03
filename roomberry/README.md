# Roomberry

This folder contains the back-end roomberry python code running on a pi zero W,
piggy-backing on a Roomba 630, a close cousin of the Create 2 robotics playground from iRobot.

The development system is a MacBook running macOS 12.7.4 Monterey with Xcode 14.2 installed.

All python scripts follow the roomberry*.py naming to allow for easy rsync-ing.

As of 26-11-02 we have:

roomberry.py
roomberry_calibration.py
roomberry_camera.py
roomberry_control.py
roomberry_localization.py
roomberry_map_image.py
roomberry_map_log.py
roomberry_mapper.py
roomberry_mission.py
roomberry_navigation.py
roomberry_navlink.py
roomberry_overhead.py
roomberry_phone_position.py
roomberry_reverse_monitor.py
roomberry_sensor_log.py
roomberry_startup.py
roomberry_web.py

Sub-Folders:

irobot	- Development library (exploded) implementing the roomba serial and openinterface (OI) routines
web	- light-weight web interface to control the roomberry state; also: interface to the legacy web-app (don't touch)
tools	- Deployment scripts to push updates to the pi as well as returning log and sensor data back to the mac
docs	- Development chit-chat; `overhead-ground-truth.md` describes the tile-grid calibration run
logs	- runtime logs, sensor data, map state
roomberry	- more map state (why here?)
