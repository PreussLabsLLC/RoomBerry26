"""Compatibility import for the former iRobot module location."""
# @(#) constants.py 3.2.flat.1 2026/11/19 11:56:56

import sys

import roomberry_oi_constants

sys.modules[__name__] = roomberry_oi_constants
