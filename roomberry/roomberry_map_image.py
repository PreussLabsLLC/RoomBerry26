"""On-demand PNG map rendering for Roomberry."""
# @(#)roomberry_map_image.py 2.3.6 2026/10/28 14:30:00
from collections import deque
from io import BytesIO
from math import ceil, hypot
from PIL import Image, ImageDraw


COLORS = {
    'pending': (242, 190, 75), 'mowed': (92, 170, 112),
    'excluded': (205, 83, 83), 'blocked': (88, 53, 53),
    'unreachable': (150, 150, 150), 'free': (247, 247, 240),
}

# A trail gap this large usually means localization jumped between runs (or
# recovered onto a different tag), not that the robot drove straight across the
# room. Split the line there instead of drawing a misleading shortcut.
TRAIL_GAP_MM = 275.0
TRAIL_OLDEST_COLOR = (220, 232, 246)
TRAIL_NEWEST_COLOR = (25, 100, 210)


def trail_segments(trail, gap_mm=TRAIL_GAP_MM):
    """Split a world-frame trail wherever consecutive poses jump too far."""
    segments = []
    current = []
    for point in trail:
        point = (float(point[0]), float(point[1]))
        if current and hypot(point[0] - current[-1][0],
                             point[1] - current[-1][1]) > gap_mm:
            if len(current) > 1:
                segments.append(current)
            current = []
        current.append(point)
    if len(current) > 1:
        segments.append(current)
    return segments


def _fade_color(fraction):
    """Blend the old-trail color into the current color as fraction rises."""
    fraction = min(1.0, max(0.0, float(fraction))) ** 3
    return tuple(
        int(round(old + (new - old) * fraction))
        for old, new in zip(TRAIL_OLDEST_COLOR, TRAIL_NEWEST_COLOR)
    )


def render_map(state, tags=()):
    cols, rows = state['cols'], state['rows']
    pitch = float(state['cell_size_mm'])
    ox, oy = float(state['origin_x']), float(state['origin_y'])
    scale = max(2, min(12, 720 // max(cols, rows)))
    left, top, right_margin, bottom_margin = 56, 42, 20, 56
    plot_width, plot_height = cols * scale, rows * scale
    right, bottom = left + plot_width, top + plot_height
    width, height = right + right_margin, bottom + bottom_margin
    im = Image.new('RGB', (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(im)

    occ, cookies = state['occupancy'], state['cookies']
    blocked = {
        (x, y) for y in range(rows) for x in range(cols)
        if occ[y][x] == 'blocked'
    }
    clearance = set()
    radius = float(state.get('robot_radius_mm', pitch * 2))
    reach = int(radius / pitch) + 1
    for x, y in blocked:
        for yy in range(max(0, y - reach), min(rows, y + reach + 1)):
            for xx in range(max(0, x - reach), min(cols, x + reach + 1)):
                if hypot(xx - x, yy - y) * pitch <= radius:
                    clearance.add((xx, yy))

    pose = state.get('pose')
    reachable = set()
    if pose and pose.get('cell') and pose['cell'] not in blocked | clearance:
        start = tuple(pose['cell'])
        reachable = {start}
        queue = deque([start])
        while queue:
            x, y = queue.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                neighbor = (x + dx, y + dy)
                if (not (0 <= neighbor[0] < cols and 0 <= neighbor[1] < rows)
                        or neighbor in reachable or neighbor in blocked | clearance):
                    continue
                if dx and dy and ((x + dx, y) in blocked | clearance or
                                  (x, y + dy) in blocked | clearance):
                    continue
                reachable.add(neighbor)
                queue.append(neighbor)

    def xy(x, y):
        return (left + (float(x) - ox) / pitch * scale,
                top + (rows - (float(y) - oy) / pitch) * scale)

    for y in range(rows):
        for x in range(cols):
            cookie = cookies[y][x]
            color = COLORS['blocked'] if occ[y][x] == 'blocked' else COLORS[cookie]
            if cookie == 'pending' and pose and (x, y) not in reachable:
                color = COLORS['unreachable']
            cell_left = left + x * scale
            cell_top = top + (rows - y - 1) * scale
            draw.rectangle((cell_left, cell_top,
                            cell_left + scale - 1, cell_top + scale - 1),
                           fill=color, outline=(220, 220, 215))

    draw.rectangle((left, top, right, bottom), outline=(25, 25, 25), width=3)
    trail = state.get('trail', [])
    segments = trail_segments(trail)
    pair_count = sum(max(0, len(segment) - 1) for segment in segments)
    # Composite onto the actual cell colors so old paths fade into the map
    # rather than becoming pale opaque lines over obstacles and coverage.
    trail_layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    trail_draw = ImageDraw.Draw(trail_layer)
    pair_index = 0
    for segment in segments:
        for start, end in zip(segment, segment[1:]):
            fraction = pair_index / max(1, pair_count - 1)
            # Keep the only line of a short trail fully visible.
            if pair_count == 1:
                fraction = 1.0
            pair_index += 1
            opacity = int(round(255 * (0.03 + 0.97 * fraction ** 3)))
            trail_draw.line(
                (xy(*start), xy(*end)),
                fill=_fade_color(fraction) + (opacity,),
                width=max(2, scale // 2),
            )
    im = Image.alpha_composite(im.convert('RGBA'), trail_layer).convert('RGB')
    draw = ImageDraw.Draw(im)
    for x, y, tag_id in tags:
        px, py = xy(x, y)
        radius_px = max(4, scale)
        draw.ellipse((px - radius_px, py - radius_px,
                      px + radius_px, py + radius_px),
                     fill=(35, 95, 190), outline='white', width=2)
        draw.text((px + radius_px + 2, py - radius_px), str(tag_id),
                  fill=(15, 50, 120))
    if pose:
        x, y = pose['x_mm'], pose['y_mm']
        px, py = xy(x, y)
        radius_px = max(5, scale * 1.4)
        draw.ellipse((px - radius_px, py - radius_px,
                      px + radius_px, py + radius_px),
                     fill=(30, 90, 220), outline='white', width=2)
        import math
        draw.line((px, py,
                   px + math.cos(pose['heading_rad']) * radius_px * 2,
                   py - math.sin(pose['heading_rad']) * radius_px * 2),
                  fill=(20, 40, 130), width=3)

    # Minor ticks every 500 mm; labeled major ticks every 1000 mm.
    minor_step, major_step = 500.0, 1000.0
    x_min, x_max = ox, ox + cols * pitch
    y_min, y_max = oy, oy + rows * pitch
    for value in range(int(ceil(x_min / minor_step) * minor_step),
                       int(x_max) + 1, int(minor_step)):
        px, _ = xy(value, oy)
        major = value % int(major_step) == 0
        tick = 7 if major else 4
        draw.line((px, bottom, px, bottom + tick), fill=(25, 25, 25), width=1)
        if major:
            label = str(value)
            box = draw.textbbox((0, 0), label)
            draw.text((px - (box[2] - box[0]) / 2, bottom + 9), label,
                      fill=(25, 25, 25))

    for value in range(int(ceil(y_min / minor_step) * minor_step),
                       int(y_max) + 1, int(minor_step)):
        _, py = xy(ox, value)
        major = value % int(major_step) == 0
        tick = 7 if major else 4
        draw.line((left - tick, py, left, py), fill=(25, 25, 25), width=1)
        if major:
            label = str(value)
            box = draw.textbbox((0, 0), label)
            draw.text((left - tick - 4 - (box[2] - box[0]),
                       py - (box[3] - box[1]) / 2), label,
                      fill=(25, 25, 25))

    draw.text((left + plot_width / 2 - 18, bottom + 34), 'X (mm)',
              fill=(25, 25, 25))
    y_label = Image.new('RGBA', (48, 14), (255, 255, 255, 0))
    ImageDraw.Draw(y_label).text((0, 0), 'Y (mm)', fill=(25, 25, 25))
    y_label = y_label.rotate(90, expand=True)
    im.paste(y_label, (3, top + (plot_height - y_label.height) // 2), y_label)

    # Keep the legend in the top margin, clear of the coordinate labels.
    legend = [('Cleaned', COLORS['mowed']), ('Not visited', COLORS['pending']),
              ('Unreachable', COLORS['unreachable']), ('Blocked', COLORS['blocked'])]
    x_cursor, legend_y = 8, 8
    for label, color in legend:
        draw.rectangle((x_cursor, legend_y, x_cursor + 11, legend_y + 11),
                       fill=color)
        draw.text((x_cursor + 15, legend_y - 1), label, fill=(30, 30, 30))
        box = draw.textbbox((0, 0), label)
        x_cursor += 22 + box[2] - box[0]
    draw.text((left + 330, 8), 'Ticks: 500 mm minor / 1000 mm labeled',
              fill=(30, 30, 30))

    output = BytesIO()
    im.save(output, format='PNG', optimize=True)
    return output.getvalue()