"""
Tests for project configuration and structure
"""
from pathlib import Path


class TestProjectConfiguration:
    """Test project configuration files"""

    def test_environment_yml_exists(self):
        """Test that environment.yml exists"""
        project_root = Path(__file__).parent.parent
        env_file = project_root / "environment.yml"
        assert env_file.exists(), "environment.yml not found at project root"

    def test_environment_yml_has_content(self):
        """Test that environment.yml has proper content"""
        project_root = Path(__file__).parent.parent
        env_file = project_root / "environment.yml"
        content = env_file.read_text()
        assert "python" in content.lower(), "environment.yml should specify python"
        assert "pytest" in content.lower(), "environment.yml should include pytest"

    def test_readme_exists(self):
        """Test that README.md exists"""
        project_root = Path(__file__).parent.parent
        readme = project_root / "README.md"
        assert readme.exists(), "README.md not found"

    def test_github_workflows_exist(self):
        """Test that GitHub workflows are configured"""
        project_root = Path(__file__).parent.parent
        workflows_dir = project_root / ".github" / "workflows"
        assert workflows_dir.exists(), ".github/workflows directory not found"

    def test_python_package_conda_workflow_exists(self):
        """Test that python-package-conda.yml workflow exists"""
        project_root = Path(__file__).parent.parent
        workflow_file = project_root / ".github" / \
            "workflows" / "python-package-conda.yml"
        assert workflow_file.exists(), "python-package-conda.yml workflow not found"


class TestFilePermissions:
    """Test that files are readable"""

    def test_main_code_project_readable(self):
        """Test that MAIN_CODE_PROJECT is accessible"""
        project_root = Path(__file__).parent.parent
        main_code = project_root / "MAIN_CODE_PROJECT"
        assert main_code.is_dir(), "MAIN_CODE_PROJECT should be a directory"

    def test_fetch_details_py_exists(self):
        """Test that fetch_details.py exists"""
        project_root = Path(__file__).parent.parent
        fetch_file = project_root / "MAIN_CODE_PROJECT" / "fetch_details.py"
        assert fetch_file.exists(), "fetch_details.py not found"

    def test_get_request_py_exists(self):
        """Test that get_request.py exists"""
        project_root = Path(__file__).parent.parent
        get_req_file = project_root / "MAIN_CODE_PROJECT" / "get_request.py"
        assert get_req_file.exists(), "get_request.py not found"


class TestWeek1Structure:
    """Test Week 1 challenge structure"""

    def test_week1_directory_exists(self):
        """Test that week-1 directory exists"""
        project_root = Path(__file__).parent.parent
        week1_dir = project_root / "MAIN_CODE_PROJECT" / "week-1"
        assert week1_dir.exists(), "week-1 directory not found"

    def test_week1_has_days(self):
        """Test that week-1 has day directories"""
        project_root = Path(__file__).parent.parent
        week1_dir = project_root / "MAIN_CODE_PROJECT" / "week-1"

        expected_days = ["day-1", "day-2", "day-3",
                         "day-4", "day-5", "day-6", "day-7"]
        for day in expected_days:
            day_path = week1_dir / day
            assert day_path.exists(), f"{day} directory not found in week-1"
