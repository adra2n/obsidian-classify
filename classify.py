#!/usr/bin/env python3
"""兼容入口：python classify.py scan"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from obsidian_classify.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
