import serial
import time
import struct

PORT = '/dev/serial0'
BAUD = 115200

try:
    ser = serial.Serial(PORT, baudrate=BAUD, timeout=2.0)
    
    # Initialize Open Interface to Passive Mode
    ser.write(b'\x80')  # Opcode 128: START
    time.sleep(0.1)
    
    # Request Packet ID 100 (Full 80-byte telemetry array)
    ser.write(struct.pack('BB', 142, 100))
    data = ser.read(80)
    
    if len(data) == 80:
        print("\n================ ROOMBA 80-BYTE SENSOR DUMP ================")
        
        # Unpacking standard signed/unsigned metrics based on the iRobot Spec
        bumps_drops = data[0]
        wall = data[1]
        cliff_l = data[2]
        cliff_fl = data[3]
        cliff_fr = data[4]
        cliff_r = data[5]
        v_wall = data[6]
        wheel_overcurrents = data[7]
        dirt_detect = data[8]
        # data[9] unused padding byte
        remote_opcode = data[10]
        buttons = data[11]
        
        distance, = struct.unpack('>h', data[12:14])
        angle,    = struct.unpack('>h', data[14:16])
        
        charging_state = data[16]
        voltage_mv,    = struct.unpack('>H', data[17:19])
        current_ma,    = struct.unpack('>h', data[19:21])
        temperature    = data[21]
        battery_charge, = struct.unpack('>H', data[22:24])
        capacity_mah,  = struct.unpack('>H', data[24:26]) # Packet 100 splits capacity sizes
        
        wall_signal,   = struct.unpack('>H', data[26:28])
        cliff_l_sig,   = struct.unpack('>H', data[28:30])
        cliff_fl_sig,  = struct.unpack('>H', data[30:32])
        cliff_fr_sig,  = struct.unpack('>H', data[32:34])
        cliff_r_sig,   = struct.unpack('>H', data[34:36])
        
        # Unused padding/charging system registers
        oi_mode = data[41]
        song_number = data[42]
        song_playing = data[43]
        
        requested_velocity, = struct.unpack('>h', data[48:50])
        requested_radius,   = struct.unpack('>h', data[50:52])
        requested_r_speed,  = struct.unpack('>h', data[52:54])
        requested_l_speed,  = struct.unpack('>h', data[54:56])
        left_encoder,       = struct.unpack('>h', data[56:58])
        right_encoder,      = struct.unpack('>h', data[58:60])
        stasis = data[79]

        # --- Print out human readable data ---
        print(f"[Core System Variables]")
        print(f"  OI Mode:                  {oi_mode} (0=Off, 1=Passive, 2=Safe)")
        print(f"  Battery Voltage:          {voltage_mv / 1000.0:.2f} V")
        print(f"  Current Amperage:         {current_ma} mA")
        print(f"  Internal Temperature:     {temperature} °C")
        print(f"  Charge Capacity Remaining:{battery_charge} mAh")
        print(f"  Estimated Full Capacity:  {capacity_mah} mAh")
        print(f"  Charging State Identifier:{charging_state} (4 = Recovery/Reconditioning)")
        
        print(f"\n[Environment & Bumpers]")
        print(f"  Bumps & Wheel Drops Byte:  {bin(bumps_drops)} (Bit 0=R, 1=L, 2=RWheel, 3=LWheel)")
        print(f"  Wall Sensor Detected:     {bool(wall)} (Analog Signal Strength: {wall_signal})")
        print(f"  Dirt Detect Level:        {dirt_detect}")
        print(f"  Virtual Wall Infrared RX: {bool(v_wall)}")
        print(f"  Physical Buttons Pressed: {bin(buttons)}")
        
        print(f"\n[Cliff Ground Infrared Sensors]")
        print(f"  Cliff Left:               {bool(cliff_l)} (Signal: {cliff_l_sig})")
        print(f"  Cliff Front Left:         {bool(cliff_fl)} (Signal: {cliff_fl_sig})")
        print(f"  Cliff Front Right:        {bool(cliff_fr)} (Signal: {cliff_fr_sig})")
        print(f"  Cliff Right:              {bool(cliff_r)} (Signal: {cliff_r_sig})")
        
        print(f"\n[Navigation & Odometry]")
        print(f"  Distance Traveled (mm):   {distance}")
        print(f"  Angle Rotated (degrees):  {angle}")
        print(f"  Left Wheel Encoder Count: {left_encoder}")
        print(f"  Right Wheel Encoder Count:{right_encoder}")
        print(f"  Stasis Forward Progress:  {stasis}")
        print("============================================================\n")
    else:
        print(f"Error: Expected 80 bytes but only read {len(data)} bytes. Try waking the frame.")

except Exception as e:
    print(f"Execution Error: {e}")
finally:
    ser.write(b'\xAD')  # Opcode AD: STOP
    time.sleep(0.1)
    if 'ser' in locals() and ser.is_open:
        ser.close()

