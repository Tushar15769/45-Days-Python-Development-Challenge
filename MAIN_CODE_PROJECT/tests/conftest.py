"""
Pytest configuration and shared fixtures
"""
import sys
import os
from pathlib import Path

# Add MAIN_CODE_PROJECT to path so we can import modules
project_root = Path(__file__).parent.parent
main_code_project = project_root / "MAIN_CODE_PROJECT"
sys.path.insert(0, str(main_code_project))

# Change to MAIN_CODE_PROJECT directory for imports to work
os.chdir(str(main_code_project))
