"""Grid mapping and cookie-mowing mission planning for Roomberry.

This module is deliberately independent of the HTTP server, camera, and Roomba
serial driver. A localization/mission coordinator can feed it world-frame poses
and obstacle observations, then send its next waypoint to RobotCommandArbiter.

Coordinates are millimeters in a fixed room frame. The map origin is the lower
left corner; heading is radians counter-clockwise from +X.
"""

# @(#)roomberry_mapper.py 2.3.recovery.1 2026/10/30 17:25:00
from collections import deque
from math import ceil, cos, hypot, floor, isfinite, sin
from threading import Lock, RLock
from time import monotonic
import json
import os


PERSIST_INTERVAL_S = 30.0
MOTION_PADDING_MM = 20.0
MOTION_SAMPLE_FRACTION = 0.25

FREE = 'free'
BLOCKED = 'blocked'
COOKIE_PENDING = 'pending'
COOKIE_MOWED = 'mowed'
COOKIE_EXCLUDED = 'excluded'


def footprint_clearance_radius(robot_radius_mm, pitch):
    return robot_radius_mm + MOTION_PADDING_MM + pitch*MOTION_SAMPLE_FRACTION/2


def obstacle_clearance_cells(cols, rows, pitch, robot_radius_mm, obstacles):
    """Inflate whole blocked squares by the same radius as motion checking."""
    radius = footprint_clearance_radius(robot_radius_mm, pitch)
    reach = ceil(radius/pitch)+1
    clearance = set()
    for col,row in obstacles:
        for yy in range(max(0,row-reach),min(rows,row+reach+1)):
            for xx in range(max(0,col-reach),min(cols,col+reach+1)):
                cx,cy=(xx+.5)*pitch,(yy+.5)*pitch
                dx=max(col*pitch-cx,0,cx-(col+1)*pitch)
                dy=max(row*pitch-cy,0,cy-(row+1)*pitch)
                if hypot(dx,dy)<=radius:clearance.add((xx,yy))
    return clearance


class RoomberryMapper:
    """Finite grid map and nearest-reachable un-mowed-cookie planner.

    ``cols`` and ``rows`` describe a known cleaning playfield, not a map
    inferred from sensors. Cells begin traversable so a mission can start in a
    bounded room; mark furniture and newly discovered hazards as obstacles.
    A cell is a cookie target, while ``record_cleaned_sweep`` accounts for the
    vacuum covering several nearby targets in one pass.

    The default cell spacing is half the Roomba radius. For obstacle safety,
    whole blocked squares are inflated by the robot footprint and motion margin
    before choosing path cells, matching the short-motion clearance checks.
    ``plan_next`` returns a waypoint only; it never drives the robot.
    """

    def __init__(self, cols, rows, robot_radius_mm, origin=(0.0, 0.0),
                 cell_size_mm=None, cleaning_radius_mm=None,
                 persist_interval_s=PERSIST_INTERVAL_S):
        if int(cols) <= 0 or int(rows) <= 0:
            raise ValueError('Map dimensions must be positive')
        if float(robot_radius_mm) <= 0:
            raise ValueError('Robot radius must be positive')
        self.cols = int(cols)
        self.rows = int(rows)
        self.robot_radius_mm = float(robot_radius_mm)
        self.cell_size_mm = float(cell_size_mm or robot_radius_mm / 2.0)
        if self.cell_size_mm <= 0:
            raise ValueError('Cell spacing must be positive')
        self.cleaning_radius_mm = float(
            cleaning_radius_mm if cleaning_radius_mm is not None
            else robot_radius_mm * 0.5
        )
        self.origin_x, self.origin_y = map(float, origin)
        self.persist_interval_s = max(0.0, float(persist_interval_s))
        self._lock = RLock()
        self._persist_lock = Lock()
        self._last_persist = None
        self._dirty = False
        self._occupancy = [[FREE for _ in range(self.cols)] for _ in range(self.rows)]
        self._cookies = [[COOKIE_PENDING for _ in range(self.cols)] for _ in range(self.rows)]
        self._pose = None
        self._localized = False
        self._obstacle_cells = set()
        self._clearance_cells = set()
        self._trail = []
        self._trail_session_start = 0
        self.state_path = None

    def save_state(self, filename=None):
        filename = filename or self.state_path
        if not filename: return
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
        with self._lock:
            state = {"cols":self.cols,"rows":self.rows,"cell_size_mm":self.cell_size_mm,
                     "origin_x":self.origin_x,"origin_y":self.origin_y,
                     "robot_radius_mm":self.robot_radius_mm,"occupancy":self._occupancy,
                     "cookies":self._cookies,"trail":list(self._trail),
                     "trail_session_start":self._trail_session_start}
        temp=filename+".tmp"
        with open(temp,"w") as f:
            json.dump(state,f,separators=(",",":")); f.flush(); os.fsync(f.fileno())
        os.replace(temp,filename)
        with self._lock:
            self._last_persist = monotonic()

    def load_state(self, filename):
        try:
            with open(filename) as f: state=json.load(f)
        except FileNotFoundError: return False
        keys=("cols","rows","cell_size_mm","origin_x","origin_y","robot_radius_mm")
        current=(self.cols,self.rows,self.cell_size_mm,self.origin_x,self.origin_y,self.robot_radius_mm)
        if tuple(state.get(k) for k in keys)!=current: raise ValueError("Saved map dimensions differ")
        occ,cookies=state["occupancy"],state["cookies"]
        if len(occ)!=self.rows or len(cookies)!=self.rows or any(len(r)!=self.cols for r in occ+cookies):
            raise ValueError("Saved map grid dimensions differ")
        with self._lock:
            self._occupancy,self._cookies=occ,cookies
            self._obstacle_cells={(x,y) for y in range(self.rows) for x in range(self.cols) if occ[y][x]==BLOCKED}
            self._clearance_cells=obstacle_clearance_cells(
                self.cols,self.rows,self.cell_size_mm,self.robot_radius_mm,self._obstacle_cells)
            self._trail=[tuple(v) for v in state.get("trail",[])][-2000:]
            # Loading begins a new recording session. Retained points belong
            # to previous runs even if the prior file marked them current.
            self._trail_session_start = len(self._trail)
            self._pose=None; self._localized=False
            self._dirty=False
            self._last_persist=None
        self.state_path=filename
        return True

    def snapshot(self):
        with self._lock:
            return {"cols":self.cols,"rows":self.rows,"cell_size_mm":self.cell_size_mm,
                    "origin_x":self.origin_x,"origin_y":self.origin_y,
                    "robot_radius_mm":self.robot_radius_mm,
                    "occupancy":[list(r) for r in self._occupancy],"cookies":[list(r) for r in self._cookies],
                    "pose":None if self._pose is None else dict(self._pose),"trail":list(self._trail),
                    "trail_session_start":self._trail_session_start}

    def _persist(self, force=False):
        """Write pending changes, at most once per ``persist_interval_s``.

        The full grid is a large JSON document. Coverage updates occur every
        mission tick, so writing on each change would fsync the SD card several
        times a second. The map stays authoritative in memory; ``flush`` saves
        it immediately at mode changes and shutdown.
        """
        if not self.state_path:
            return False
        with self._persist_lock:
            with self._lock:
                if not self._dirty:
                    return False
                now = monotonic()
                if (not force and self._last_persist is not None and
                        now - self._last_persist < self.persist_interval_s):
                    return False
                # Clear before the write so changes made during file I/O are
                # left dirty and will be persisted on the next pass.
                self._dirty = False
            try:
                self.save_state()
            except Exception:
                with self._lock:
                    self._dirty = True
                raise
        return True

    def flush(self):
        """Persist any pending map changes immediately."""
        return self._persist(force=True)

    @property
    def bounds_mm(self):
        """Playfield extent as (width, height)."""
        return self.cols * self.cell_size_mm, self.rows * self.cell_size_mm

    def world_to_cell(self, x_mm, y_mm):
        """Return (column, row), or None when outside the mapped playfield."""
        col = int(floor((float(x_mm) - self.origin_x) / self.cell_size_mm))
        row = int(floor((float(y_mm) - self.origin_y) / self.cell_size_mm))
        if 0 <= col < self.cols and 0 <= row < self.rows:
            return col, row
        return None

    def cell_center(self, cell):
        col, row = cell
        self._require_cell(col, row)
        return (
            self.origin_x + (col + 0.5) * self.cell_size_mm,
            self.origin_y + (row + 0.5) * self.cell_size_mm,
        )

    def update_pose(self, x_mm, y_mm, heading_rad, localized=True):
        """Set the latest fused pose. Unlocalized poses disable route planning."""
        cell = self.world_to_cell(x_mm, y_mm)
        recorded = False
        with self._lock:
            self._pose = {
                'x_mm': float(x_mm), 'y_mm': float(y_mm),
                'heading_rad': float(heading_rad), 'cell': cell,
            }
            self._localized = bool(localized and cell is not None)
            if self._localized:
                pt=(float(x_mm),float(y_mm))
                if (len(self._trail) == self._trail_session_start or
                        hypot(pt[0]-self._trail[-1][0],pt[1]-self._trail[-1][1])>=self.cell_size_mm*0.5):
                    # Bound only loaded history, never truncate this session.
                    self._trail.append(pt)
                    self._dirty = True
                    recorded = True
        if recorded: self._persist()

    def mark_obstacle(self, x_mm, y_mm, radius_mm=None):
        """Mark an observed obstacle point and optional physical radius."""
        obstacle = self.world_to_cell(x_mm, y_mm)
        if obstacle is None:
            return False
        radius = max(0.0, float(radius_mm or 0.0))
        with self._lock:
            self._add_obstacle_cell(*obstacle)
            if radius:
                reach = int(floor(radius / self.cell_size_mm))
                for row in range(max(0, obstacle[1] - reach),
                                 min(self.rows, obstacle[1] + reach + 1)):
                    for col in range(max(0, obstacle[0] - reach),
                                     min(self.cols, obstacle[0] + reach + 1)):
                        if hypot(col - obstacle[0], row - obstacle[1]) * self.cell_size_mm <= radius:
                            self._add_obstacle_cell(col, row)
            self._dirty = True
        self._persist()
        return True

    def clear_nearby_obstacles(self, x_mm, y_mm, radius_mm=500.0):
        """Forget local map observations for a bounded blocked-route retry."""
        if not all(isfinite(float(v)) for v in (x_mm, y_mm, radius_mm)) or radius_mm < 0:
            raise ValueError('Obstacle clearing requires finite coordinates and a nonnegative radius')
        with self._lock:
            removed = {cell for cell in self._obstacle_cells
                       if hypot(self.cell_center(cell)[0] - x_mm,
                                self.cell_center(cell)[1] - y_mm) <= radius_mm}
            for col, row in removed:
                self._occupancy[row][col] = FREE
                self._cookies[row][col] = COOKIE_PENDING
            self._obstacle_cells.difference_update(removed)
            if removed:
                self._clearance_cells = obstacle_clearance_cells(
                    self.cols, self.rows, self.cell_size_mm,
                    self.robot_radius_mm, self._obstacle_cells)
                self._dirty = True
        if removed:
            self._persist()
        return len(removed)

    def mark_free(self, x_mm, y_mm):
        """Mark an observed cell free; an obstacle observation remains authoritative."""
        cell = self.world_to_cell(x_mm, y_mm)
        if cell is None:
            return False
        col, row = cell
        with self._lock:
            if cell not in self._obstacle_cells:
                self._occupancy[row][col] = FREE
                self._dirty = True
        self._persist()
        return True

    def record_cleaned_sweep(self, x_mm, y_mm, radius_mm=None):
        """Mark cookie targets covered by the vacuum's path as mowed."""
        radius = self.cleaning_radius_mm if radius_mm is None else max(0.0, float(radius_mm))
        changed = False
        with self._lock:
            for row in range(self.rows):
                for col in range(self.cols):
                    if self._cookies[row][col] != COOKIE_PENDING:
                        continue
                    cx, cy = self.cell_center((col, row))
                    if hypot(cx - float(x_mm), cy - float(y_mm)) <= radius:
                        self._cookies[row][col] = COOKIE_MOWED
                        changed = True
            if changed:
                self._dirty = True
        if changed: self._persist()

    def plan_next(self):
        """Return the next shortest-path waypoint, or None if no route is available.

        Result keys: ``target`` is the cookie cell to pursue, ``waypoint`` is
        the next cell along a route, ``waypoint_mm`` is its center, and
        ``path`` contains all cells from the robot's current cell to target.
        Ties are stable in row/column order so plans are reproducible.
        """
        with self._lock:
            if not self._localized or self._pose is None or self._pose['cell'] is None:
                return None
            start = self._pose['cell']
            if not self._is_traversable(start):
                return None
            parents, distances = self._reachable_tree(start)
            candidates = []
            for row in range(self.rows):
                for col in range(self.cols):
                    cell = (col, row)
                    if (self._cookies[row][col] == COOKIE_PENDING and
                            cell in distances and self._is_traversable(cell)):
                        candidates.append((distances[cell], row, col, cell))
            if not candidates:
                return None
            _, _, _, target = min(candidates)
            path = self._build_path(parents, target)
            waypoint = path[1] if len(path) > 1 else target
            return {
                'target': target,
                'waypoint': waypoint,
                'waypoint_mm': self.cell_center(waypoint),
                'path': path,
            }

    def plan_to(self, x_mm, y_mm):
        """Plan to a known world coordinate, such as a mapped charging dock."""
        target = self.world_to_cell(x_mm, y_mm)
        if target is None:
            return None
        with self._lock:
            if not self._localized or self._pose is None or self._pose['cell'] is None:
                return None
            start = self._pose['cell']
            if not self._is_traversable(start) or not self._is_traversable(target):
                return None
            parents, distances = self._reachable_tree(start)
            if target not in distances:
                return None
            path = self._build_path(parents, target)
            waypoint = path[1] if len(path) > 1 else target
            return {
                'target': target,
                'waypoint': waypoint,
                'waypoint_mm': self.cell_center(waypoint),
                'path': path,
            }

    def motion_is_clear(self, pose, velocity_mm_s, yaw_rad_s, duration_s):
        """Check a short commanded arc's footprint against known map geometry.

        Sample at most a quarter-cell apart and pad the robot footprint by
        half that spacing plus 20 mm for steering changes. Unknown furniture
        still requires the controller's independent bumper/cliff protection.
        """
        x, y, heading = (float(pose[k]) for k in ('x_mm', 'y_mm', 'heading_rad'))
        velocity, yaw, duration = map(float, (velocity_mm_s, yaw_rad_s, duration_s))
        if not all(isfinite(v) for v in (x, y, heading, velocity, yaw, duration)):
            return False
        if duration <= 0:
            return False
        spacing = self.cell_size_mm * MOTION_SAMPLE_FRACTION
        steps = max(1, ceil(abs(velocity) * duration / spacing))
        footprint_radius = self.robot_radius_mm + spacing / 2.0
        radius = footprint_radius + MOTION_PADDING_MM
        pitch, ox, oy = self.cell_size_mm, self.origin_x, self.origin_y
        initial_edges = (x-ox, ox+self.cols*pitch-x,
                         y-oy, oy+self.rows*pitch-y)
        with self._lock:
            def obstacle_distance(px, py, col, row):
                dx = max(ox + col * pitch - px, 0.0, px - (ox + (col + 1) * pitch))
                dy = max(oy + row * pitch - py, 0.0, py - (oy + (row + 1) * pitch))
                return hypot(dx, dy)

            obstacles = [(col, row, obstacle_distance(x, y, col, row))
                         for col, row in self._obstacle_cells]
            for step in range(steps + 1):
                t = duration * step / steps
                if abs(yaw) < 1e-6:
                    px, py = x + velocity * t * cos(heading), y + velocity * t * sin(heading)
                else:
                    px = x + velocity / yaw * (sin(heading + yaw * t) - sin(heading))
                    py = y - velocity / yaw * (cos(heading + yaw * t) - cos(heading))
                edges = (px-ox, ox+self.cols*pitch-px,
                         py-oy, oy+self.rows*pitch-py)
                for clearance, initial in zip(edges, initial_edges):
                    if clearance <= footprint_radius:
                        return False
                    if initial <= radius:
                        if clearance < initial-1e-6:
                            return False
                    elif clearance < radius:
                        return False
                for col, row, initial_distance in obstacles:
                    # Distance from the center to the entire blocked square,
                    # rather than just its center, protects obstacle corners.
                    distance = obstacle_distance(px, py, col, row)
                    if distance <= footprint_radius:
                        return False
                    # A new contact or pose correction can leave the robot
                    # inside just the extra comfort padding. Permit an escape
                    # without reducing its starting clearance, preserving the
                    # actual footprint and sampling margin throughout.
                    if initial_distance <= radius:
                        if distance < initial_distance - 1e-6:
                            return False
                    elif distance <= radius:
                        return False
        return True

    def status(self):
        """Return a compact mission/map summary suitable for a UI or logger."""
        with self._lock:
            pending = sum(cell == COOKIE_PENDING for row in self._cookies for cell in row)
            mowed = sum(cell == COOKIE_MOWED for row in self._cookies for cell in row)
            excluded = sum(cell == COOKIE_EXCLUDED for row in self._cookies for cell in row)
            return {
                'localized': self._localized,
                'pose': None if self._pose is None else dict(self._pose),
                'pending_cookies': pending,
                'mowed_cookies': mowed,
                'excluded_cookies': excluded,
                'obstacles': len(self._obstacle_cells),
                'total_cookies': self.cols * self.rows,
            }

    def cell_state(self, col, row):
        """Expose a cell's occupancy and cookie state for visualization/debugging."""
        self._require_cell(col, row)
        with self._lock:
            return {
                'occupancy': self._occupancy[row][col],
                'cookie': self._cookies[row][col],
            }

    def _reachable_tree(self, start):
        parents = {start: None}
        distances = {start: 0}
        queue = deque([start])
        while queue:
            col, row = queue.popleft()
            for neighbor in self._neighbors(col, row):
                if neighbor in parents or not self._is_traversable(neighbor):
                    continue
                # Avoid squeezing diagonally between two blocked cells.
                dx, dy = neighbor[0] - col, neighbor[1] - row
                if dx and dy and (
                        not self._is_traversable((col + dx, row)) or
                        not self._is_traversable((col, row + dy))):
                    continue
                parents[neighbor] = (col, row)
                distances[neighbor] = distances[(col, row)] + 1
                queue.append(neighbor)
        return parents, distances

    @staticmethod
    def _build_path(parents, target):
        path = []
        cell = target
        while cell is not None:
            path.append(cell)
            cell = parents[cell]
        return list(reversed(path))

    def _add_obstacle_cell(self, col, row):
        cell = (col, row)
        self._obstacle_cells.add(cell)
        self._occupancy[row][col] = BLOCKED
        self._cookies[row][col] = COOKIE_EXCLUDED
        self._clearance_cells.update(obstacle_clearance_cells(
            self.cols,self.rows,self.cell_size_mm,self.robot_radius_mm,[(col,row)]))

    def _neighbors(self, col, row):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                x, y = col + dx, row + dy
                if 0 <= x < self.cols and 0 <= y < self.rows:
                    yield x, y

    def _is_traversable(self, cell):
        col, row = cell
        # A free grid cell is not a valid center waypoint if the robot would
        # extend outside the room. Match the short-motion boundary allowance.
        inset = footprint_clearance_radius(self.robot_radius_mm,self.cell_size_mm)
        x, y = (col+0.5)*self.cell_size_mm, (row+0.5)*self.cell_size_mm
        if not (inset <= x <= self.cols*self.cell_size_mm-inset and
                inset <= y <= self.rows*self.cell_size_mm-inset):
            return False
        return (self._occupancy[row][col] == FREE and
                cell not in self._clearance_cells)

    def _require_cell(self, col, row):
        if not (0 <= int(col) < self.cols and 0 <= int(row) < self.rows):
            raise ValueError('Cell is outside the map')

