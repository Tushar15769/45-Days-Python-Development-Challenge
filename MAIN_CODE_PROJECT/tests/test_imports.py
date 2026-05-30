"""
Basic tests to verify that core modules can be imported
"""
import sys
from pathlib import Path


class TestBasicImports:
    """Test that basic Python modules work"""

    def test_json_module(self):
        """Test importing json module"""
        import json
        assert json is not None

    def test_datetime_module(self):
        """Test importing datetime module"""
        from datetime import datetime, timedelta
        assert datetime is not None
        assert timedelta is not None

    def test_pathlib_module(self):
        """Test importing pathlib module"""
        from pathlib import Path
        assert Path is not None

    def test_dataclasses_module(self):
        """Test importing dataclasses module"""
        from dataclasses import dataclass, field
        assert dataclass is not None
        assert field is not None


class TestProjectStructure:
    """Test that project structure is correct"""

    def test_main_code_project_exists(self):
        """Test that MAIN_CODE_PROJECT directory exists"""
        project_root = Path(__file__).parent.parent
        main_code_dir = project_root / "MAIN_CODE_PROJECT"
        assert main_code_dir.exists(
        ), f"MAIN_CODE_PROJECT not found at {main_code_dir}"

    def test_src_directory_exists(self):
        """Test that src directory exists"""
        project_root = Path(__file__).parent.parent
        src_dir = project_root / "MAIN_CODE_PROJECT" / "src"
        assert src_dir.exists(), f"src directory not found at {src_dir}"

    def test_src_files_exist(self):
        """Test that key src files exist"""
        project_root = Path(__file__).parent.parent
        src_dir = project_root / "MAIN_CODE_PROJECT" / "src"

        expected_files = [
            "banking_simulation.py",
            "cli_calculator.py",
            "contact_manager.py",
            "password_generator.py",
            "task_management.py",
        ]

        for file in expected_files:
            file_path = src_dir / file
            assert file_path.exists(
            ), f"Expected file {file} not found in src directory"
