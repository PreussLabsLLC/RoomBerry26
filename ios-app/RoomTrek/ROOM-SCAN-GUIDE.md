<!-- @(#)ROOM-SCAN-GUIDE.md 3.1.roomtrek.3 2026/11/08 14:30:00 -->
# RoomTrek: scan, transfer and test a room map

Use **Sputnik (iPhone 11 Pro)** to survey and **Peters 10 (iPhone X)** to test
localization. This creates an ARKit feature map, not a floor plan or room mesh.
Cross-phone map compatibility and accuracy are still being tested.

## 1. Prepare both phones and the room

1. Confirm RoomTrek opens on both phones. Sputnik has the Save Map fix; the
   iPhone X also needs RoomTrek installed before the import/test steps.
2. Allow camera access. Hold or mount each phone in landscape, rear camera
   looking outward. Clean the lenses.
3. Leave **NavLink telemetry OFF** on both phones. It is unnecessary for this
   test; the current Pi receiver does not support RoomTrek's map-pose packets.
4. Use steady room lighting and leave furniture in the same positions throughout
   surveying and testing. Open doors to the positions you intend to test with.
5. Mark a starting position **A**, a measured checkpoint **B**, and a return
   route. Choose visible landmarks near each, such as a cabinet corner or
   doorway. Record the measured A-to-B distance.
6. Mark camera height and facing direction at A and B. Measurements refer to
   the camera, so place each phone's rear camera at the same marks when testing.
   For robot use, survey at the intended mounted camera height.

## 2. Survey with Sputnik

1. Open RoomTrek and select **Surveyor**.
2. Position the rear camera at A, facing the chosen landmarks.
3. Tap **Start Survey**. The button changes to **Stop**.
4. Move slowly, with smooth turns, so the camera sees textured cabinets,
   doorframes, furniture and wall details. Avoid pointing only at a blank wall
   or the floor. The feature dots show detected features, not completed coverage.
5. Follow an overlapping loop through the intended test area, including B.
   Revisit previously seen landmarks rather than only moving into new space.
6. Return to A at the original camera height and facing direction.
7. Check tracking is normal. Prefer mapping **extending** or **mapped** before
   saving; these statuses do not certify full room coverage or accuracy. If
   tracking is limited, move slowly toward recognizable details and wait.

## 3. Save the survey on Sputnik

1. Scroll the control panel to the map-name field. Enter a recognizable name,
   such as `Kitchen-01`. Add a note with lighting, camera height and route.
2. Tap **Save Map** while the survey is still running. This is the simplest
   first test. The updated app also permits **Stop**, then **Save Map**, before
   you start another session; that paused capture path still needs a phone test.
3. Look for **Saving Map…**, then the **Map saved.** confirmation. Dismiss it.
   If an error appears, record its exact wording. Do not assume a map was saved.
4. Scroll to **Map library (tap to select)** and verify the new name appears.
   Tap that row so it has a checkmark; a newly saved row is not necessarily
   selected if an older map was already selected.
5. Tap **Stop** if the survey is still running. A saved map persists after
   stopping or closing the app. An unsaved survey does not survive app restart.

## 4. Export and move the map to Peters 10

1. On Sputnik, select the saved map's row in RoomTrek.
2. Tap **Export Selected Map**. This opens a Files export picker.
3. Choose a folder you can find again, such as **On My iPhone → RoomTrek**,
   then confirm **Save/Export** as offered by the picker.
4. Open **Files** on Sputnik and locate the exported `.roomtrek` file. Its
   filename may be a UUID rather than the friendly map name. Keep the extension.
5. For AirDrop, keep both phones nearby and unlocked, enable Wi-Fi and Bluetooth,
   and disable Personal Hotspot. On Peters 10, use **Settings → General → AirDrop**
   and temporarily choose **Everyone for 10 Minutes** if Contacts Only does not work.
6. In Files on Sputnik, touch and hold the exported file, choose **Share → AirDrop**,
   and select **Peters 10**. Accept on Peters 10 if prompted.
7. On Peters 10, save or locate the received file in **Files**. If iOS asks which
   app to use, choose Files when available. Confirm you can find the `.roomtrek`
   file before continuing. Receiving it does not itself import it into RoomTrek.

AirDrop controls and receive prompts vary by iOS release; see
[Apple's AirDrop instructions](https://support.apple.com/en-ie/119857).
If AirDrop is inconvenient, use a shared Files location such as iCloud Drive,
wait for the file to download on Peters 10, then use the same import steps below.
The RoomTrek app itself has no cloud-sync service.

## 5. Import on Peters 10

1. Open RoomTrek. Stop any running session.
2. Tap **Import Map (Files)** and browse to the transferred `.roomtrek` file.
3. Select it and wait for the **Imported “name”.** confirmation.
4. Verify the expected friendly name appears in the map library with a checkmark.
   If import fails, record the error and retain the original Sputnik map/file.
   A failure may reveal cross-version ARKit archive incompatibility; successful
   transfer alone does not prove the map can be used by the older phone.
5. Select **Navigator** and confirm the intended map remains selected.

## 6. Test localization on Peters 10

1. Put its rear camera at A at the survey height, facing the same landmarks.
2. Tap **Start Navigator** and start timing.
3. Slowly look around the nearby landmarks with small movements. Watch for
   **RELOCALIZING**, then **LOCALIZED (candidate)** and **Valid: YES**. The app
   requires observed relocalizing followed by at least one second of normal
   tracking before marking a candidate valid.
4. Record the time to that candidate and the displayed x, y, z and yaw at A.
   They need not be zero: this is the saved map's coordinate system.
5. Move slowly along the surveyed route to B. At the measured camera position
   and facing direction, record x, y, z, yaw and validity again.
6. Return to A, align the camera to the original marks and record the same values.
   A small difference from the first A reading measures return consistency.
7. Compare horizontal distance from A to B using
   `sqrt((xB − xA)^2 + (yB − yA)^2)` in metres. Compare return error using the
   same formula for initial A and final A. The displayed Z axis is vertical.
   Multiply metres by 100 for centimetres.
8. Use **30.48 cm (one foot)** as the initial investigation target for both
   checkpoint distance error and return error. This is a test target, not a
   promised accuracy. A good return alone can hide errors along the route.
9. Tap **Stop**, then **Export Log + Pose CSV**, and save/share both log files.
   Export before closing the app to keep the run easy to identify.

## 7. Repeat and record results

Use the same imported map for at least three trials. Start from different
surveyed locations or facing directions and use **Reset / Retry** during an
active Navigator session to begin a fresh localization attempt. After each
reset, wait for a new valid candidate before taking measurements.

Record one row per trial:

| Trial | Map name / ID shown | Start location/facing | Time to candidate | Measured A–B | Reported A–B | Return error | Tracking losses / notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |

Also record phone/OS, camera height and lighting. Keep failed attempts in the
record. If no candidate appears after about a minute, stop and record the
attempt as unsuccessful; this is a practical test cutoff, not an app timeout.

## If something does not work

- **Save Map is gray:** select Surveyor and start a survey first. After Stop,
  saving requires the updated app and the same retained survey session.
- **Saving fails after Stop:** note the error, start a fresh survey and save
  while running. Do not restart before saving a survey you want to retain.
- **Saved map missing from export:** select its library row explicitly first.
- **File arrived but library is empty:** use Import Map (Files) inside RoomTrek.
- **Import fails:** keep the file and error text; do not treat this as a failed
  scan until archive compatibility and file integrity have been checked.
- **Tracking is NORMAL but not LOCALIZED / Valid YES:** tap Reset / Retry and
  look at surveyed landmarks. Normal tracking alone does not pass the app's
  relocalization gate.
- **LOST or Valid NO during the route:** pause measurements, revisit recognizable
  landmarks and wait for a valid candidate again. Record the interruption.
