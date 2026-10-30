# Roomberry

**Roomberry 26** follows the original roomberry project (Pi Zero W with picam riding on
Roomba 630). The goal here is to evolve the camera rover into a more capable cleaning bot
using the camera and apriltags placed around the house to aid location tracking.

The architecture was updated to separate intent from actions, ie. not letting the web-app
control motors directly. Other changes were to separate the camera handling, mapping, localization, and
mission strategy. Camera handling with AprilTag detection may need to move into it's own thread
as heavy cpu usage is expected and critical sensor data / motor
actions need to be maintained. A possible solution would be for the Roomba to stop every
now & then, look for april tags, and then carry on.

We spent some time trying the optimize the april tag detection by stopp ing the roomba during scans and using that
time to flush pending writes of sensor and map data to disk. But tag scanning did not seem to provide a robust enough
framework to re-align location data tracked from wheel sensors with real-world positions.

The next try will be to integrate an IOS application utilizing ARKit to track movements and positions by scanning
the ceiling from an iphone riding upside-down on the Roomba.

[MicroDuck Architecture](https://github.com/pollen-robotics/microduck/blob/main/docs/design/architecture.md)

**Roomberry** is a surveillance robot based on **Roomba** using a **Raspberry Pi Zero W** and a **camera module**. A demo of Roomberry's capabilities as well as the web interface developed to interact with the robot can be seen in the following video:

[![Roomberry Demo](https://domoticproject.com/wp-content/uploads/2018/08/RoomberryDemoVisualCue.png)](https://www.youtube.com/watch?&v=kQcQSE5pvNA "Roomberry Demo")

## Requirements

To build this project you will need:
-	A **mini DIN 7 male connector** (DIN 8 is compatible too) with Roomba's pin 3 (RxD), 4 (TxD) and 5 (BRC).
-	A compatible **Roomba** (series 600/700/800) adapted to provide a regulated 5 V power source direct from the battery using an step-down (Pololu D24V5F5 is a good option).
-	A **Raspberry Pi Zero W** with Raspberry Pi OS and the Picamera2 package installed, along with the pyserial library and an adapted version of Matthew Witherwax' Python iRobot [library](https://github.com/danimaciasperea/irobot). Picamera2 requires a recent Raspberry Pi OS release with `python3-picamera2` and `python3-pil` installed.
-	A **Raspberry camera module** (I used Version 1).
-	A HAT (Hardware Attached on Top) board to connect Raspberry's GPIO with a **Logical Level Converter** (Roomba's Serial is 5 V compatible but Raspberry uses 3.3 V).
<p align="center">
<img src="https://domoticproject.com/wp-content/uploads/2018/08/Roofino_Roomba_RaspberryPiZeroW_Camera2.jpg">
</p>
<p align="center">
<img src="https://domoticproject.com/wp-content/uploads/2018/08/Roomberry-Front-View.jpg">
</p>

## How it works

`Roomberry.py` creates a **multithreading python web server** that interacts with Roomba and the camera module installed. This code is intended to run as a daemon and handles the HTTP GET Requests performed against the Raspberry Pi.

To install it just download the last release and configure it as a service:
```bash
wget https://github.com/danimaciasperea/Roomberry/archive/1.0.0.tar.gz -P /tmp/
tar -xvf /tmp/1.0.0.tar.gz -C /tmp/

# Before doing next step, adapt the code to your environment (serial port used, IFTTT Key, etc.)
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry.py /usr/local/bin/
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry_camera.py /usr/local/bin/
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry_control.py /usr/local/bin/
sudo cp /tmp/Roomberry-1.0.0/roomberry/roomberry.service /lib/systemd/system/

sudo systemctl enable roomberry.service
sudo system roomberry start

```

The commands sent to the robot are encoded in the **request's  URL query string**. The URL path should start with `cam` or `roomba` depending on the device that will execute the operation. If the command needs one or more parameters, they should be just passed as a field-value pair in the query string.

For instance:

```bash
#Send a clean command to Roomba
curl roomberry/roomba/?op=clean

#Drive Roomba straight at 20 mm/s
curl roomberry/roomba/?op=drive&velocity=20&radius=32768

#Set camera saturation to 65
curl roomberry/cam/?op=cam&saturation=65

#Download picture taken the 10th 08 2018 at 10:28:49
wget roomberry/cam/20180810/20180810-102849.jpg
```

To use the **web interface** you will need a Raspberry running `apache2` with `PHP` enabled. Just deploy the web-application on the web server path. For instance:

```bash
sudo cp -R /tmp/Roomberry-1.0.0/web-app/ /var/www/
```

It has been designed using Bootstrap framework (HTML5 and Javascript with AJAX requests). You will probably need to adapt the `HTML` code to your particular needs/environment.

<p align="center">
<img src="https://domoticproject.com/wp-content/uploads/2018/08/Screen-capture-WebInterface-Roomberry.png">
</p>

Find the complete instructions on how to build this project in the following [post](https://domoticproject.com/roomberry-surveillance-robot-roomba-raspberry-pi-zero-w-camera/).

## License
This project is licensed under the MIT License - see the  [license file](LICENSE.md) for details

## Legal Notice
Roomba is a trademark of iRobot Corporation. All other trademarks are the property of their respective owners.

## Acknowledgments

-  Matthew Witherwax' Python iRobot [library](https://github.com/julianpistorius/irobot).
-  Picamera [package](https://github.com/waveform80/picamera).



