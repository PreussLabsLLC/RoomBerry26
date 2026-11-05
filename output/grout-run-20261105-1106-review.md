<!-- @(#)grout-run-20261105-1106-review.md 3.1.grout.18 2026/11/05 -->
# 11:06 session: endpoint overrun and repeated return interruptions

Source: roomberry/logs/roomberry.log, session 20261105-110632; associated sensor
and NavLink archives uploaded. Distances below are wheel estimates, not measured
floor distances; wheel slip and manual intervention make them especially uncertain.

## Outbound

Four initial starts11:06:42–51 were rejected for safety/contact. Next run began
11:06:56 and stopped11:07:14 on line/phone telemetry validity. Its stripe dropout
11:07:05.646 at914mm recovered by11:07:06.253 at940mm.

Restart11:07:21 reset the run origin. Sustained stripe loss began11:07:48.515
at2773mm in that run. It still commanded low-speed reverse, with12.19s reported
loss at11:08:00.704 and3081mm wheel displacement. Right motor sustained current
.477A at11:07:56.052 was report-only. At11:08:00.906 the run aborted for wheel
travel opposite the commanded direction. No successful threshold marker was
recorded. The .17 sensitivity window starting4000mm could not help this restarted
run: it did not reach4000mm relative to its new origin. Physical spinning was
reported by the user; wheel current and untrusted odometry are compatible with it.

## Return

-11:09:19/32/46 line handoffs repeatedly lost stripe after motion, invoking
 mapped-tag recovery three times. Initial distant scans had no reliable mapped fix.
-11:09:58 and11:13:15 sensor poll failures read56/80 and32/80bytes respectively,
 causing sensor-not-ready stops. These are serial-read failures, not tag rejection.
-11:10:52 a653.96mm tag discrepancy correctly requested stationary confirmation,
 but phone telemetry validity aborted the next scan at11:10:53.823.
-11:11:37–48 consecutive stationary tag poses jumped about166mm then985mm,
 beyond75mm/4deg agreement.11:12:20–30 shifts were about189mm and213mm.
 These are inconsistent poses even without trusting wheel prediction; the new
 confirmation rule correctly did not accept them. No tolerance relaxed in .18.
-11:13:11 and11:16:49 eventually confirmed localization.11:17:11 also confirmed
 relocation despite wheel-heading discrepancy, demonstrating .17 recovery worked.
-11:17:25/29 final checkpoint confirmed; line-following approach continued at30mm/s.
 At11:17:41 it reached its approach position/travel bound without bumper contact.
 Retained range then119.2mm, below the124mm (174mm radius minus50mm) lower bound.
 Three tag-recovery handoffs reused the same near-target trace and immediately
 encountered the bound again; final abort11:18:10.198. This is not a confirmed
 arrival or a reliable measurement of actual clearance. The near-target retry
 loop and pose reliability remain follow-up issues; the guard was not relaxed.

## Implemented .18

First fresh explicit no-stripe report hard-brakes and ends motion lease, at any
outbound distance. Confirm while stationary for1s with at least3 distinct loss
frames, then mark endpoint and return. Three fresh high-confidence stripe frames
cancel the check and resume. Ambiguity times out stopped after3s. Stale/invalid
telemetry still aborts; it cannot identify the endpoint. An unrelated sustained
stripe loss can therefore cause early return, intentionally avoiding blind travel.

Phone events remain logged/guarded at normal .6g with existing150ms transient
suppression, but reacted outbound impacts stop to idle rather than marking a
successful threshold. Distance-gated .17 threshold sensitivity is superseded.
No changes to return localization/arrival bounds in this patch.141 tests passed,
including differential-drive out/back with real tag geometry, brief-loss recovery,
stationary endpoint confirmation, repeated packet rejection and stale telemetry.
Local only; user syncs Pi modules/restarts .18. No phone rebuild or physical commands.
