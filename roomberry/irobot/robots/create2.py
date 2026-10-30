__author__ = 'Matthew Witherwax (lemoneer)'
__maintainer__ = "Daniel Macías Perea (dani.macias.perea@domoticproject.com)"

import types
from time import sleep, time
import logging
import serial
from six import raise_from, iterbytes
import RPi.GPIO as GPIO

from irobot.openinterface.commands import set_mode_full, set_mode_passive, set_mode_safe, power_down, reset, start, stop, \
    drive, drive_direct, drive_pwm, seek_dock, set_baud, set_day_time, set_schedule, clean, clean_max, clean_spot, \
    set_motors, set_motors_pwm, set_leds, set_ascii_leds, trigger_buttons, set_song, play_song, request_sensor_data, \
    set_scheduling_leds, set_raw_leds
from irobot.openinterface.constants import BAUD_RATE, DRIVE, RESPONSE_SIZES, ROBOT, MODES, POWER_SAVE_TIME
from serial.serialutil import SerialException

from irobot.openinterface.response_parsers import binary_response, byte_response, unsigned_byte_response, short_response, \
    unsigned_short_response, BumpsAndWheelDrop, WheelOvercurrents, Buttons, ChargingSources, LightBumper, Stasis, \
    SensorGroup0, SensorGroup1, SensorGroup2, SensorGroup3, SensorGroup4, SensorGroup5, SensorGroup6, SensorGroup100, \
    SensorGroup101, SensorGroup106, SensorGroup107

_error_msg_range = 'Argument {0} out of range'


class Create2(object):
    def __init__(self, port, brc_pin=0, baud_rate=115200, timeout=1, auto_wake=True, enable_quirks=True):
        self._auto_wake = auto_wake
        self._oi_mode = MODES.OFF
        self._last_command_time = time()

        self._enable_quirks = enable_quirks
        self._toggle_quirks()

        self.logger = logging.getLogger('Create2')

        #If Roomba BRC pin is set , configure GPIO as wake up pin and configure correct wake function
        self._brc_pin = brc_pin
        if (self._brc_pin != 0):
            self.wake = types.MethodType(Create2._wake_BRC, self)
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self._brc_pin, GPIO.OUT)
            GPIO.output(self._brc_pin, True)
            sleep(1)
            GPIO.output(self._brc_pin, False)
            sleep(1)
            GPIO.output(self._brc_pin, True)
        else:
            self.wake = types.MethodType(Create2._wake_RTS, self)

        self._attach_to_robot(port, baud_rate, timeout)



    def __del__(self):
        serial_port = getattr(self, '_serial_port', None)
        if serial_port is not None:
            try:
                self.stop()
            except Exception:
                pass
            try:
                serial_port.close()
            except Exception:
                pass
        if getattr(self, '_brc_pin', 0) != 0:
            try:
                GPIO.cleanup()
            except Exception:
                pass

    def _attach_to_robot(self, port, baud_rate, timeout):
        try:
            self._serial_port = serial.Serial(port=port,
                                              baudrate=baud_rate,
                                              bytesize=serial.EIGHTBITS,
                                              parity=serial.PARITY_NONE,
                                              stopbits=serial.STOPBITS_ONE,
                                              timeout=timeout,
                                              writeTimeout=timeout,
                                              xonxoff=False,
                                              rtscts=False,
                                              dsrdtr=False)
        except SerialException as e:
            raise_from(RobotConnectionError(port, baud_rate), e)

        # wait for the robot to wake up on connection opened
        sleep(1)

        try:
            self.start()
        except Exception:
            try:
                self._wake_without_brc()
                self.start()
            except Exception:
                self._serial_port.close()
                raise

    def _wake_without_brc(self):
        """Use the utility-verified START/RESET sequence to wake without BRC."""
        self.logger.info('Attempting serial START/RESET wake sequence.')
        self._serial_port.reset_input_buffer()
        self._serial_port.write(start())
        sleep(0.1)
        self._serial_port.write(reset())

        deadline = time() + 15.0
        last_data = None
        received = 0
        while time() < deadline:
            data = self._serial_port.read(1024)
            if data:
                received += len(data)
                last_data = time()
            elif last_data is not None and time() - last_data >= 1.0:
                break

        self._serial_port.reset_input_buffer()
        self._last_command_time = time()
        self.logger.info('Serial wake sequence received %d boot bytes.', received)

    def _send(self, data):
        self._log_send(data)

        self._handle_auto_wake()

        #Roomba will sleep after 5 minutes of inactivity.
        #Requesting a data packet is not considered as activity.
        if (data[0] != 142):
            self._last_command_time = time()

        self._serial_port.write(data)

    def _read_sensor_data(self, id):
        #Flush input buffer to avoid inconsistent reads
        self._serial_port.reset_input_buffer()

        self._send(request_sensor_data(id))
        size = RESPONSE_SIZES[id]
        data = self._serial_port.read(size)

        #If no data was received, wake the roomba JIC
        if len(data) != size:
            self.wake()
            raise IOError('Received %d bytes but %d were expected' % (len(data), size))

        self.logger.info('Received\n{0}'.format(self._format_data(data)))

        return data

    def _handle_auto_wake(self):
        if not self._auto_wake or self._oi_mode != MODES.PASSIVE:
            return

        now = time()
        # wake the robot if the last command was sent any time after power saves
        if (now - self._last_command_time) >= POWER_SAVE_TIME :
            self.wake()

    def _log_send(self, data):
        self.logger.info('Last command sent {0:.2f} seconds ago\nSending Command\n{1}'.format(
            time() - self._last_command_time,
            self._format_data(data)
        ))

    @staticmethod
    def _format_data(data):
        data = iterbytes(data)
        return 'Decimal:\t[{0}]\nHex:\t\t[{1}]\nBin:\t\t[{2}]'.format(
            '|'.join(('{0:d}'.format(b)) for b in data),
            '|'.join(('{0:X}'.format(b)) for b in data),
            '|'.join(('{0:08b}'.format(b)) for b in data)
        )

    def _toggle_quirks(self):
        if self._enable_quirks:
            self._get_distance = types.MethodType(Create2._get_distance_quirks, self)
            self._get_angle = types.MethodType(Create2._get_angle_quirks, self)
        else:
            self._get_distance = types.MethodType(Create2._get_distance_std, self)
            self._get_angle = types.MethodType(Create2._get_angle_std, self)

    def _change_mode(self, mode):
        if mode == MODES.PASSIVE:
            mode_cmd = set_mode_passive()
        elif mode == MODES.SAFE:
            mode_cmd = set_mode_safe()
        elif mode == MODES.FULL:
            mode_cmd = set_mode_full()
        else:
            raise ValueError('Invalid mode')

        self._send(mode_cmd)
        self._verify_mode(mode)

    def _verify_mode(self, mode):
        if self.oi_mode != mode:
            raise ModeChangeError(mode, self._oi_mode)

    @staticmethod
    def _is_valid_hour(hour):
        return 0 <= hour <= 23

    @staticmethod
    def _is_valid_minute(minute):
        return 0 <= minute <= 59

    @property
    def enable_quirks(self):
        return self._enable_quirks

    @enable_quirks.setter
    def enable_quirks(self, value):
        self._enable_quirks = value
        self._toggle_quirks()

    @property
    def auto_wake(self):
        return self._auto_wake

    @auto_wake.setter
    def auto_wake(self, value):
        self._auto_wake = value

    def wake(self):
        pass

    def _wake_BRC(self):
        self.logger.info('Waking robot after {0:.2f} seconds of inactivity'.format(time() - self._last_command_time))
        GPIO.output(self._brc_pin, False)
        sleep(1)
        GPIO.output(self._brc_pin, True)
        sleep(1)
        # after a wake up the robot sends some information. Flush it!
        self._serial_port.reset_input_buffer()
        self._last_command_time = time()

    def _wake_RTS(self):
        self.logger.info('Waking robot after {0:.2f} seconds of inactivity'.format(time() - self._last_command_time))
        self._serial_port.setRTS(True)  # rts in pyserial 3.0
        sleep(1)
        self._serial_port.setRTS(False)
        sleep(1)
        self._serial_port.setRTS(True)
        sleep(1)
        # after a wake up the robot sends some information. Flush it!
        self._serial_port.reset_input_buffer()
        self._last_command_time = time()

    def start(self):
        self._send(start())

        # read data waiting on start
        welcome_message = self._serial_port.read(1024).decode('utf-8')
        if welcome_message is not None:
            self.logger.info('First 1024 characters of welcome message: {0}'.format(welcome_message))
        # flush anything after the first 1024 bytes
        self._serial_port.reset_input_buffer()

        self._verify_mode(MODES.PASSIVE)

    def reset(self):
        self._send(reset())
        self._oi_mode = MODES.OFF

    def stop(self):
        self._send(stop())
        self._oi_mode = MODES.OFF

    def set_baud(self, baud=BAUD_RATE.DEFAULT):
        self._send(set_baud(baud))

    def clean(self):
        self._send(clean())
        self._verify_mode(MODES.PASSIVE)

    def clean_max(self):
        self._send(clean_max())
        self._verify_mode(MODES.PASSIVE)

    def clean_spot(self):
        self._send(clean_spot())
        self._verify_mode(MODES.PASSIVE)

    def seek_dock(self):
        self._send(seek_dock())
        self._verify_mode(MODES.PASSIVE)

    def power_down(self):
        self._send(power_down())
        self._oi_mode = MODES.OFF

    def set_schedule(self, sun_hour=0, sun_min=0, mon_hour=0, mon_min=0, tues_hour=0, tues_min=0, wed_hour=0,
                     wed_min=0, thurs_hour=0, thurs_min=0, fri_hour=0, fri_min=0, sat_hour=0, sat_min=0):

        if not self._is_valid_hour(sun_hour):
            raise ValueError(_error_msg_range.format('sun_hour'))
        if not self._is_valid_hour(mon_hour):
            raise ValueError(_error_msg_range.format('mon_hour'))
        if not self._is_valid_hour(tues_hour):
            raise ValueError(_error_msg_range.format('tues_hour'))
        if not self._is_valid_hour(wed_hour):
            raise ValueError(_error_msg_range.format('wed_hour'))
        if not self._is_valid_hour(thurs_hour):
            raise ValueError(_error_msg_range.format('thurs_hour'))
        if not self._is_valid_hour(fri_hour):
            raise ValueError(_error_msg_range.format('fri_hour'))
        if not self._is_valid_hour(sat_hour):
            raise ValueError(_error_msg_range.format('sat_hour'))

        if not self._is_valid_minute(sun_min):
            raise ValueError(_error_msg_range.format('sun_min'))
        if not self._is_valid_minute(mon_min):
            raise ValueError(_error_msg_range.format('mon_min'))
        if not self._is_valid_minute(tues_min):
            raise ValueError(_error_msg_range.format('tues_min'))
        if not self._is_valid_minute(wed_min):
            raise ValueError(_error_msg_range.format('wed_min'))
        if not self._is_valid_minute(thurs_min):
            raise ValueError(_error_msg_range.format('thurs_min'))
        if not self._is_valid_minute(fri_min):
            raise ValueError(_error_msg_range.format('fri_min'))
        if not self._is_valid_minute(sat_min):
            raise ValueError(_error_msg_range.format('sat_min'))

        self._send(
            set_schedule(sun_hour, sun_min, mon_hour, mon_min, tues_hour, tues_min, wed_hour, wed_min, thurs_hour,
                         thurs_min, fri_hour, fri_min, sat_hour, sat_min))

    def clear_schedule(self):
        self._send(self.schedule())

    def set_day_time(self, day=0, hour=0, minute=0):
        if not 0 <= day <= 6:
            raise ValueError(_error_msg_range.format('day'))
        if not self._is_valid_hour(hour):
            raise ValueError(_error_msg_range.format('hour'))
        if not self._is_valid_minute(minute):
            raise ValueError(_error_msg_range.format('minute'))
        self._send(set_day_time(day, hour, minute))

    def drive(self, velocity, radius):
        if not -500 <= velocity <= 500:
            raise ValueError(_error_msg_range.format('velocity'))
        if not -2000 <= radius <= 2000 and\
                (radius != DRIVE.STRAIGHT and radius != DRIVE.STRAIGHT_ALT
                 and radius != DRIVE.TURN_IN_PLACE_CCW and radius != DRIVE.TURN_IN_PLACE_CW):
            raise ValueError(_error_msg_range.format('radius'))

        self._send(drive(velocity, radius))

    def drive_straight(self, velocity):
        self.drive(velocity, DRIVE.STRAIGHT)

    def spin_left(self, velocity):
        self.drive(velocity, DRIVE.TURN_IN_PLACE_CCW)

    def spin_right(self, velocity):
        self.drive(velocity, DRIVE.TURN_IN_PLACE_CW)

    def drive_direct(self, right_velocity, left_velocity):
        if not -500 <= right_velocity <= 500:
            raise ValueError(_error_msg_range.format('right_velocity'))
        if not -500 <= left_velocity <= 500:
            raise ValueError(_error_msg_range.format('left_velocity'))

        self._send(drive_direct(right_velocity, left_velocity))

    def drive_pwm(self, right_pwm, left_pwm):
        if not -255 <= right_pwm <= 255:
            raise ValueError(_error_msg_range.format('right_pwm'))
        if not -255 <= left_pwm <= 255:
            raise ValueError(_error_msg_range.format('left_pwm'))
        self._send(drive_pwm(right_pwm, left_pwm))

    def set_motors(self, main_brush_on=False, main_brush_reverse=False, side_brush=False, side_brush_reverse=False,
                   vacuum=False):
        self._send(set_motors(main_brush_on, main_brush_reverse, side_brush, side_brush_reverse, vacuum))

    def set_motors_pwm(self, main_brush_pwm, side_brush_pwm, vacuum_pwm):
        if not -127 <= main_brush_pwm <= 127:
            raise ValueError(_error_msg_range.format('main_brush_pwm'))
        if not -127 <= side_brush_pwm <= 127:
            raise ValueError(_error_msg_range.format('side_brush_pwm'))
        if not 0 <= vacuum_pwm <= 127:
            raise ValueError(_error_msg_range.format('vacuum_pwm'))

        self._send(set_motors_pwm(main_brush_pwm, side_brush_pwm, vacuum_pwm))

    def set_leds(self, debris=False, spot=False, dock=False, check_robot=False, power_color=0, power_intensity=0):
        if not 0 <= power_color <= 255:
            raise ValueError(_error_msg_range.format('power_color'))
        if not 0 <= power_intensity <= 255:
            raise ValueError(_error_msg_range.format('power_intensity'))

        self._send(set_leds(debris, spot, dock, check_robot, power_color, power_intensity))

    def set_scheduling_leds(self, sun=False, mon=False, tues=False, wed=False, thurs=False, fri=False, sat=False,
                            schedule=False, clock=False, am=False, pm=False, colon=False):
        self._send(set_scheduling_leds(sun, mon, tues, wed, thurs, fri, sat, schedule, clock, am, pm, colon))

    def set_raw_leds(self, digit1=0, digit2=0, digit3=0, digit4=0):
        """
        Arguments - ORed set of segments to turn on
        ex RAW_LED.A | RAW_LED.B | RAW_LED.C
        """
        self._send(set_raw_leds(digit1, digit2, digit3, digit4))

    def set_ascii_leds(self, char1=32, char2=32, char3=32, char4=32):
        self._send(set_ascii_leds(char1, char2, char3, char4))

    def trigger_buttons(self, clean=False, spot=False, dock=False, minute=False, hour=False, day=False, schedule=False, clock=False):
        self._send(trigger_buttons(clean, spot, dock, minute, hour, day, schedule, clock))

    def set_song(self, song_number, notes):
        if not 0 <= song_number <= 3:
            raise ValueError(_error_msg_range.format('song_number'))

        num_notes = len(notes)
        if not 0 < num_notes <= 16:
            raise ValueError('Length of notes out of range')

        for i in range(0, num_notes):
            note = notes[i]
            if not 31 <= note[0] <= 127:
                note[0] = 0

            if not 0 <= note[1] <= 255:
                raise ValueError(_error_msg_range.format('notes' + '[' + i + '][1]'))

        self._send(set_song(song_number, notes))

    def play_song(self, song_number):
        if not 0 <= song_number <= 3:
            pass
        self._send(play_song(song_number))

    @property
    def bumps_and_wheel_drops(self):
        return BumpsAndWheelDrop(self._read_sensor_data(7))

    @property
    def wall_sensor(self):
        return binary_response(self._read_sensor_data(8))

    @property
    def cliff_left(self):
        return binary_response(self._read_sensor_data(9))

    @property
    def cliff_front_left(self):
        return binary_response(self._read_sensor_data(10))

    @property
    def cliff_front_right(self):
        return binary_response(self._read_sensor_data(11))

    @property
    def cliff_right(self):
        return binary_response(self._read_sensor_data(12))

    @property
    def virtual_wall(self):
        return binary_response(self._read_sensor_data(13))

    @property
    def wheel_overcurrents(self):
        return WheelOvercurrents(self._read_sensor_data(14))

    @property
    def dirt_detect(self):
        return byte_response(self._read_sensor_data(15))

    @property
    def ir_char_omni(self):
        return unsigned_byte_response(self._read_sensor_data(17))

    @property
    def ir_char_left(self):
        return unsigned_byte_response(self._read_sensor_data(52))

    @property
    def ir_char_right(self):
        return unsigned_byte_response(self._read_sensor_data(53))

    @property
    def buttons(self):
        return Buttons(self._read_sensor_data(18))

    @property
    def distance(self):
        return self._get_distance()

    @property
    def angle(self):
        return self._get_angle()

    def _get_distance(self):
        pass

    def _get_angle(self):
        pass

    def _get_distance_std(self):
        return short_response(self._read_sensor_data(19))

    def _get_angle_std(self):
        return short_response(self._read_sensor_data(20))

    def _get_distance_quirks(self):
        """
        As detailed in the OI Spec Create 2 and Roomba 500/600
        firmware versions prior to 3.3.0 return an incorrect
        value for distance measured in millimeters

        This calculates the distance from the raw encoder counts
        """
        left = self.left_encoder_counts
        right = self.right_encoder_counts
        return (left * ROBOT.TICK_TO_DISTANCE + right * ROBOT.TICK_TO_DISTANCE) / 2

    def _get_angle_quirks(self):
        """
        As detailed in the OI Spec Create 2 and Roomba firmware
        versions 3.4.0 and earlier return an incorrect value for
        angle measured in degrees.

        This calculates the angle from the raw encoder counts
        """
        left = self.left_encoder_counts
        right = self.right_encoder_counts
        return (right * ROBOT.TICK_TO_DISTANCE - left * ROBOT.TICK_TO_DISTANCE) / ROBOT.WHEEL_BASE

    @property
    def charging_state(self):
        return unsigned_byte_response(self._read_sensor_data(21))

    @property
    def voltage(self):
        return unsigned_short_response(self._read_sensor_data(22))

    @property
    def current(self):
        return short_response(self._read_sensor_data(23))

    @property
    def temperature(self):
        return byte_response(self._read_sensor_data(24))

    @property
    def battery_charge(self):
        return unsigned_short_response(self._read_sensor_data(25))

    @property
    def battery_capacity(self):
        return unsigned_short_response(self._read_sensor_data(26))

    @property
    def wall_signal(self):
        return unsigned_short_response(self._read_sensor_data(27))

    @property
    def cliff_left_signal(self):
        return unsigned_short_response(self._read_sensor_data(28))

    @property
    def cliff_front_left_signal(self):
        return unsigned_short_response(self._read_sensor_data(29))

    @property
    def cliff_front_right_signal(self):
        return unsigned_short_response(self._read_sensor_data(30))

    @property
    def cliff_right_signal(self):
        return unsigned_short_response(self._read_sensor_data(31))

    @property
    def charging_sources(self):
        return ChargingSources(self._read_sensor_data(34))

    @property
    def oi_mode(self):
        self._oi_mode = unsigned_byte_response(self._read_sensor_data(35))
        return self._oi_mode

    @oi_mode.setter
    def oi_mode(self, value):
        self._change_mode(value)

    @property
    def song_number(self):
        return unsigned_byte_response(self._read_sensor_data(36))

    @property
    def is_song_playing(self):
        return binary_response(self._read_sensor_data(37))

    @property
    def number_stream_packets(self):
        return unsigned_byte_response(self._read_sensor_data(38))

    @property
    def requested_velocity(self):
        return short_response(self._read_sensor_data(39))

    @property
    def requested_radius(self):
        return short_response(self._read_sensor_data(40))

    @property
    def requested_right_velocity(self):
        return short_response(self._read_sensor_data(41))

    @property
    def requested_left_velocity(self):
        return short_response(self._read_sensor_data(42))

    @property
    def left_encoder_counts(self):
        return short_response(self._read_sensor_data(43))

    @property
    def right_encoder_counts(self):
        return short_response(self._read_sensor_data(44))

    @property
    def light_bumper(self):
        return LightBumper(self._read_sensor_data(45))

    @property
    def light_bump_left_signal(self):
        return unsigned_short_response(self._read_sensor_data(46))

    @property
    def light_bump_front_left_signal(self):
        return unsigned_short_response(self._read_sensor_data(47))

    @property
    def light_bump_center_left_signal(self):
        return unsigned_short_response(self._read_sensor_data(48))

    @property
    def light_bump_center_right_signal(self):
        return unsigned_short_response(self._read_sensor_data(49))

    @property
    def light_bump_front_right_signal(self):
        return unsigned_short_response(self._read_sensor_data(50))

    @property
    def light_bump_right_signal(self):
        return unsigned_short_response(self._read_sensor_data(51))

    @property
    def left_motor_current(self):
        return short_response(self._read_sensor_data(54))

    @property
    def right_motor_current(self):
        return short_response(self._read_sensor_data(55))

    @property
    def main_brush_motor_current(self):
        return short_response(self._read_sensor_data(56))

    @property
    def side_brush_motor_current(self):
        return short_response(self._read_sensor_data(57))

    @property
    def stasis(self):
        return Stasis(self._read_sensor_data(58))

    @property
    def sensor_group0(self):
        return SensorGroup0(self._read_sensor_data(0))

    @property
    def sensor_group1(self):
        return SensorGroup1(self._read_sensor_data(1))

    @property
    def sensor_group2(self):
        return SensorGroup2(self._read_sensor_data(2))

    @property
    def sensor_group3(self):
        return SensorGroup3(self._read_sensor_data(3))

    @property
    def sensor_group4(self):
        return SensorGroup4(self._read_sensor_data(4))

    @property
    def sensor_group5(self):
        return SensorGroup5(self._read_sensor_data(5))

    @property
    def sensor_group6(self):
        return SensorGroup6(self._read_sensor_data(6))

    @property
    def sensor_group100(self):
        return SensorGroup100(self._read_sensor_data(100))

    @property
    def sensor_group101(self):
        return SensorGroup101(self._read_sensor_data(101))

    @property
    def sensor_group106(self):
        return SensorGroup106(self._read_sensor_data(106))

    @property
    def sensor_group107(self):
        return SensorGroup107(self._read_sensor_data(107))

    @property
    def firmware_version(self):
        self.reset()
        sleep(5)
        msg = self._serial_port.read(1024).decode('utf-8')
        self.start()
        self._serial_port.reset_input_buffer()  # reset_input_buffer() in pyserial 3.0
        return msg


class ModeChangeError(Exception):
    def __init__(self, requested_mode, actual_mode):
        self.requested_mode = requested_mode
        self.actual_mode = actual_mode


class RobotConnectionError(Exception):
    def __init__(self, port, baud):
        self.port = port
        self.baud = baud

    def __str__(self):
        return 'Failed to connect to robot on Port {} with Baud Code: {!r}'.format(self.port, self.baud)

