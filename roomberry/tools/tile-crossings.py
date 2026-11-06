#!/usr/bin/env python3
# @(#)tile-crossings.py 1.0.tiles.1 2026/11/05
"""Build the per-tile wheel-vs-tile calibration report from Pi logs.

Parses ``GridRunner crossing: {...}`` JSON lines (one per confirmed
transverse grout crossing, see roomberry_gridrunner._record_crossing)
out of a roomberry.log -- or a crossing-report line's rows -- and writes:
  * a CSV with one row per recorded crossing incl. per-span wheel delta,
    tile span (304.8 mm per tile), error mm and error %
  * a Markdown summary with per-leg mean/median error and total ratios.

Observation only: this never steers, and it does not apply any wheel
scale correction. Use the median ratio to judge the provisional factor.

Typical session::

    tools/tile-crossings.py --log roomberry/logs/roomberry.log \\
        --output output/tiles-20261105/crossings

    tools/tile-crossings.py --log roomberry/logs/roomberry.log --print
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roomberry_gridrunner import build_crossing_report  # noqa: E402

CROSSING_PREFIX = 'GridRunner crossing: '
REPORT_PREFIX = 'GridRunner crossing report: '


def parse_crossings(text):
    """Extract crossing records, preferring the final report block."""
    reports = []
    singles = []
    for line in text.splitlines():
        if REPORT_PREFIX in line:
            reports.append(json.loads(line.split(REPORT_PREFIX, 1)[1]))
        elif CROSSING_PREFIX in line:
            singles.append(json.loads(line.split(CROSSING_PREFIX, 1)[1]))
    if reports:
        return [row for row in reports[-1]['rows']], reports[-1].get('summary', {})
    return singles, {}


def fmt(value, digits=1):
    return 'n/a' if value is None else '{:.{d}f}'.format(value, d=digits)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ['count', 'missed', 'crossing_us', 'interval_s', 'y', 'confidence',
              'stage', 'direction', 'wheel_distance_mm', 'wheel_heading_deg',
              'tag_distance_mm', 'tile_mm_total', 'tile_mm_span',
              'wheel_delta_mm', 'error_mm', 'error_pct']
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_markdown(path, report):
    rows, summary = report['rows'], report['summary']
    lines = ['# Tile-crossing calibration report', '',
             'Nominal tile pitch: {:.1f} mm. Crossings: {}. Missed: {}.'.format(
                 summary.get('tile_mm', 304.8), summary.get('crossings', 0),
                 summary.get('missed', 0)),
             'Mean per-span error: {} mm. Median wheel/tile ratio: {}. '
             'Total ratio: {}. Total tile span: {} mm.'.format(
                 fmt(summary.get('mean_error_mm')), fmt(summary.get('median_ratio'), 4),
                 fmt(summary.get('total_wheel_ratio'), 4),
                 fmt(summary.get('total_tile_mm'))),
             '',
             '| count | leg stage | wheel mm | tile span mm | wheel delta mm | error mm | error % |',
             '|---:|---|---:|---:|---:|---:|---:|']
    for row in rows:
        lines.append('| {} | {} | {} | {} | {} | {} | {} |'.format(
            row['count'], row.get('stage'), fmt(row.get('wheel_distance_mm')),
            fmt(row.get('tile_mm_span')), fmt(row.get('wheel_delta_mm')),
            fmt(row.get('error_mm')), fmt(row.get('error_pct'), 2)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', required=True, help='roomberry.log to parse')
    parser.add_argument('--output', help='prefix for .csv/.md (parent dirs created)')
    parser.add_argument('--print', action='store_true', help='print rows as text')
    args = parser.parse_args(argv)
    text = Path(args.log).read_text(errors='replace')
    crossings, _ = parse_crossings(text)
    if not crossings:
        parser.error('no GridRunner crossing records in {}'.format(args.log))
    report = build_crossing_report(crossings)
    if args.output:
        write_csv(Path(args.output + '.csv'), report['rows'])
        write_markdown(Path(args.output + '.md'), report)
    if args.print or not args.output:
        for row in report['rows']:
            print('count={} stage={} wheel={} tile_span={} wheel_delta={} error_mm={} error_pct={}'.format(
                row['count'], row.get('stage'), fmt(row.get('wheel_distance_mm')),
                fmt(row.get('tile_mm_span')), fmt(row.get('wheel_delta_mm')),
                fmt(row.get('error_mm')), fmt(row.get('error_pct'), 2)))
        print('summary: {}'.format(json.dumps(report['summary'], sort_keys=True)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
