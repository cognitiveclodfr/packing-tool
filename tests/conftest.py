"""
Pytest configuration file for Packing Tool tests.

This file sets up the Python path to ensure all tests can import
from both the 'src' and 'shared' directories.
"""

import sys
from pathlib import Path

# Get the repository root directory (parent of tests directory)
repo_root = Path(__file__).parent.parent

# Add repository root to sys.path (for 'shared' module)
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Add src directory to sys.path (for src modules)
src_dir = repo_root / 'src'
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
