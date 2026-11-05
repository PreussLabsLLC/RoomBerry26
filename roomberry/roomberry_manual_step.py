"""Measured, cancellable local steering-pad movements; never timer-only drives."""
# @(#)roomberry_manual_step.py 3.1.grout.16 2026/11/05
from math import isfinite, radians
from time import monotonic

STEPS = {'left': ('angle', 5., 30, -30),
         'right': ('angle', -5., -30, 30),
         'forward': ('distance', 50., 50, 50),
         'backward': ('distance', -50., -50, -50),
         'forward_500': ('distance', 500., 100, 100),
         'backward_500': ('distance', -500., -100, -100)}  # right, left wheel speeds
STEP_TIMEOUT = 6.
LONG_STEP_TIMEOUT = 15.
# Trial compensation from the Nov 4 measured pad overshoot. Final measured
# results remain visible; this is not an assertion of physical precision.
BRAKE_LEAD = {'distance': 12., 'angle': 3.}


def _safe(mission, state):
    sensors = state.get('sensors')
    age = state.get('age')
    if (sensors is None or not state.get('ready') or age is None or not 0 <= age <= .5
            or state.get('oi_stopped') or state.get('safety_latched')
            or state.get('motion_lease_expired') or state.get('sensor_fault')
            or mission._hard_hazard_reasons(state)
            or state.get('battery_status') in ('low', 'critical', 'charging')):
        raise RuntimeError('Steering pad requires fresh, ready sensors and no safety stop')
    bumps = sensors.bumps_and_wheel_drops
    if bumps.bump_left or bumps.bump_right:
        raise RuntimeError('Steering pad blocked by bumper contact')
    if not all(isinstance(state.get(k), (int, float)) and isfinite(state[k])
               for k in ('distance', 'angle')):
        raise RuntimeError('Steering pad requires valid wheel odometry')


def _update_trace(mission, run, state):
    """Keep intentional manual steps in the retained grout pose, if still valid."""
    if run is None or run.identity is None or run.pose is None:
        return
    previous = run.odom
    if (state.get('odometry_epoch') != run.epoch or previous is None
            or abs(state['distance']-previous[0]) > 150
            or abs(radians(state['angle']-previous[1])) > .3):
        # Permit manual positioning, but never invent a return pose after an
        # unobserved push/reset. Re-align for a new run in this case.
        run.pose = None
        mission.logger.warning('Steering pad: retained grout pose invalid after unobserved movement/reset.')
        return
    run._integrate(state)


def run_step(mission, direction):
    if direction not in STEPS:
        raise ValueError('Unknown steering-pad direction')
    axis, target, right, left = STEPS[direction]
    timeout = LONG_STEP_TIMEOUT if abs(target) == 500 else STEP_TIMEOUT
    with mission._coord_lock:
        if mission._manual_step is not None:
            raise RuntimeError('A steering step is already running')
        if mission._scan_active:
            raise RuntimeError('Wait for the stationary tag scan to finish')
        initial = mission.robot_control.snapshot()
        _safe(mission, initial)
        retained = mission.gridrunner
        mission.set_mode('remote_control', wake_robot=False)
        record = dict(direction=direction.replace('_500',''), status='moving', axis=axis, target=target,
                      measured=0., reason=None)
        mission._manual_step = record
        mission._manual_step_status = record
        mission._manual_motion_until = monotonic()+timeout+1
        mission.robot_control.begin_motion_lease(.6)
    started = monotonic()
    progress_at, last_progress = started, 0.
    baseline, epoch = float(initial[axis]), initial.get('odometry_epoch')
    sign = 1 if target > 0 else -1
    try:
        with mission._coord_lock:
            if mission._manual_step is not record or mission._mode != 'remote_control':
                raise RuntimeError('Steering step cancelled before movement')
            _update_trace(mission, retained, initial)
            mission._stop_sent = False  # Mode changes must brake this direct drive.
            mission.robot_control.execute('drive_direct', right_velocity=right, left_velocity=left)
        while not mission._shutdown.is_set():
            with mission._coord_lock:
                if mission._manual_step is not record or mission._mode != 'remote_control':
                    record.update(status='cancelled', reason='another command took control')
                    return dict(record)
                state = mission.robot_control.snapshot()
                _safe(mission, state)
                if state.get('odometry_epoch') != epoch:
                    raise RuntimeError('Wheel odometry reset during steering step')
                _update_trace(mission, retained, state)
                measured = float(state[axis])-baseline
                record['measured'] = measured
                progress = sign*measured
                if progress >= abs(target)-BRAKE_LEAD[axis]:
                    record.update(status='complete', reason='predictive braking before target')
                    break
                if progress < (-3 if axis == 'distance' else -1):
                    raise RuntimeError('Wheel motion opposite steering-pad command')
                if progress-last_progress >= (1 if axis == 'distance' else .2):
                    progress_at, last_progress = monotonic(), progress
                if monotonic()-progress_at > 1.5:
                    raise RuntimeError('No wheel progress during steering step')
                if monotonic()-started > timeout:
                    raise RuntimeError('Steering step timed out')
                mission.robot_control.renew_motion_lease(.6)
            mission._shutdown.wait(.02)
        else:
            raise RuntimeError('Mission shutting down')
    except Exception as error:
        record.update(status='stopped', reason=str(error))
        raise
    finally:
        with mission._coord_lock:
            owned = mission._manual_step is record
            if owned:
                try:
                    mission.robot_control.execute('stop', timeout=2)
                except Exception:
                    # Leave the independent lease armed if braking cannot be
                    # confirmed; mode cleanup must not cancel that watchdog.
                    mission._manual_step = None
                    mission._manual_motion_until = 0.
                    record.update(status='stopped', reason='brake command failed; motion lease remains armed')
                    mission.logger.exception('Steering pad brake failed.')
                    raise
                mission.robot_control.end_motion_lease()
                mission._stop_sent = True
        # Allow a fresh sensor poll to include braking/coast in the saved trace.
        # Stop/idle and other controls may interrupt this wait at any time.
        if owned:
            until = monotonic()+.3
            while monotonic() < until and not mission._shutdown.is_set():
                mission._shutdown.wait(.02)
                with mission._coord_lock:
                    if mission._manual_step is not record:
                        break
                    state = mission.robot_control.snapshot()
                    if (state.get('age') is not None and 0 <= state['age'] <= .5
                            and state.get('odometry_epoch') == epoch
                            and all(isinstance(state.get(k), (int, float)) and isfinite(state[k])
                                    for k in ('distance', 'angle'))):
                        _update_trace(mission, retained, state)
                        record['measured'] = float(state[axis])-baseline
            with mission._coord_lock:
                if mission._manual_step is record:
                    mission._manual_motion_until = 0.
                    mission._remote_was_moving = False
                    mission.set_mode('idle', wake_robot=False)
        mission.logger.info('Steering pad result: %s', record)
    return dict(record)
