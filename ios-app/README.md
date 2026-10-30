<!-- @(#)ios-app/README.md 2.3.ios-plan.1 2026/10/29 -->
# iPhone localization for Roomberry

Design outline for an iPhone mounted rigidly on the Roomba with its rear camera facing the ceiling. ARKit estimates motion on the phone; compact UDP messages deliver robot position and heading to the Pi Zero. The Pi retains navigation, wheel odometry, obstacle handling, and all motor authority.

These documents specify proposed work. No iOS app or UDP receiver is implemented yet.

- [Implementation and calibration](implementation-plan.md): app structure, coordinate transforms, Pi integration, and delivery phases.
- [UDP protocol v1](udp-protocol.md): packets, units, timing, session identity, and receiver rules.
- [Validation plan](validation-plan.md): bench checks, room trials, failure injection, and provisional acceptance targets.

Develop with Xcode on macOS and test tracking on a physical ARKit-compatible iPhone. Select the deployment target after checking the actual phone and installed Xcode. A simulator can exercise interface/protocol code but cannot validate ceiling tracking.

The first milestone is a foreground app streaming a calibrated pose to a logging-only Pi receiver. Autonomous use follows measured tracking and failure-handling trials. ARKit is relative visual-inertial tracking, not a surveyed absolute indoor positioning system; blank ceilings, poor light, vibration, and relocalization may limit it.
