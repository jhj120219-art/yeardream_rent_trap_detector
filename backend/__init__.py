"""Resolve the team's unchanged analyst modules from machine/."""
import sys
from pathlib import Path

ANALYSIS_ROOT = Path(__file__).resolve().parents[1] / 'machine'
if str(ANALYSIS_ROOT) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_ROOT))
