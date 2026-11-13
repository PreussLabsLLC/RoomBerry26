<!-- @(#)report.md 3.2.analysis.1 2026/11/10 12:08:46 -->
# Early stop: battery event followed by reset-related serial silence

The initial driving stop was caused by the low-battery rule. Repeated sensor
timeouts began later, immediately after a separate web Reset Roomba command.

| Time | Evidence |
| --- | --- |
|12:01:15–12:02:14|First reset/startup enters sleep and receives0/1expected bytes; second startup succeeds.|
|12:02:37|Initial tag16 scan accepted.|
|12:02:42–58|Seven left15degree pad turns complete.|
|12:02:59|Forward500mm step starts.|
|12:03:02|Reported battery becomes low at28.1%; LOW_BATT speech, brake and seek-dock request.|
|12:03:03|Step ends stopped at~283mm; later encoder distance settles321.4mm.|
|12:03:16 onward|Further pad requests rejected by the low-battery safety gate.|
|12:03:34|Restart OI succeeds and starts a new odometry epoch.|
|12:03:55.382|Last valid sensor row.|
|12:03:55.864|Web raw Reset Roomba command completes its write.|
|12:03:58.976–12:04:49.905|17poll failures: Received0bytes but80were expected.|

The driver reset method sends the reboot opcode and sets its OI mode to OFF.
The direct reset web route does not follow with the normal startup/reconnect
sequence. Thus reset write completion does not confirm a responsive Open
Interface. Source and timing support an interface left off/unresponsive after
reset; they do not establish a cable failure or spontaneous serial outage as
the cause of the earlier driving stop.

The battery readings deserve separate attention. Adjacent sensor rows at
12:03:02.039 and12:03:02.198 change charge2690→757mAh, capacity constant2696mAh,
percentage99.8→28.1. Voltage14.194V and current−0.594A are unchanged across
that jump. Integrating the recorded current before this transition gives only
~4.8mAh consumption over47.6seconds, so the reported1933mAh drop cannot represent
physical discharge in that interval. Gauge re-estimation/reset behavior or a
charge-reporting problem remains plausible; battery condition cannot be
diagnosed from these records. The software uses the reported ratio, and its
configured30% threshold correctly classified28.1% as low. This was the dedicated
LOW_BATT announcement, rather than evidence that a periodic report caused a stop.

There were no sensor poll failures between the successful startup and the
battery-triggered stop. No cliff/wheel-drop trigger appears at that stop.
The phone continues normal tracking for all1486packets of one fresh session,
with one packet sequence gap. The attempt does not supply the planned round-trip
comparison or a useful before/after poster test.

The user has returned Rosie to the charger. All successful sensor rows in the
supplied copy still have home_base=0; subsequent charging cannot be confirmed
because sensor communication is lost before the copy ends. No live query or
command was issued to wake or disturb her on the dock. On a later retry, restore
the normal Roomberry/OI startup after charging and wait for fresh Sensors Ready
and a usable battery reading before beginning the test.

Source: supplied120214sensor CSV, NavLink binary, roomberry.log and local control/
driver code. Metrics in metrics.json. Read-only investigation; no code/config
changes, deployment, robot movement, reset or AR/map commands performed.
