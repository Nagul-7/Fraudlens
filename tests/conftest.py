"""Shared setup for the API tests.

The app loads its model and data by repo-relative path, so tests must run with
the repo root as the working directory and on sys.path, wherever pytest is
started from.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
