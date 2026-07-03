"""Make the repo-root ``skill_router`` package importable when pytest runs
from a plain checkout (no install step)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
