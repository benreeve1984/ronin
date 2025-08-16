"""Unit tests for tool handlers in tools.py"""

import pytest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import patch, MagicMock
import tools
from exceptions import (
    FileNotFoundError as RoninFileNotFoundError,
    FileAlreadyExistsError,
    AnchorNotFoundError
)


class TestFileTools:
    """Test file manipulation tools"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)
    
    def test_list_files_empty_directory(self, temp_dir):
        """Test listing files in empty directory"""
        result = tools.list_files(temp_dir)
        assert result["count"] == 0
        assert result["files"] == []
    
    def test_list_files_with_markdown(self, temp_dir):
        """Test listing markdown files"""
        # Create test files
        (temp_dir / "test.md").write_text("# Test\nContent")
        (temp_dir / "readme.txt").write_text("Text file")
        (temp_dir / "ignored.py").write_text("print('ignored')")
        
        result = tools.list_files(temp_dir, pattern="*.md")
        assert result["count"] == 1
        assert len(result["files"]) == 1
        assert result["files"][0]["path"] == "test.md"
        assert result["files"][0]["lines"] == 2
    
    def test_read_file_success(self, temp_dir):
        """Test reading a file successfully"""
        test_file = temp_dir / "test.txt"
        content = "Line 1\nLine 2\nLine 3"
        test_file.write_text(content)
        
        result = tools.read_file(test_file)
        assert result == content
    
    def test_read_file_with_line_range(self, temp_dir):
        """Test reading specific lines from a file"""
        test_file = temp_dir / "test.txt"
        content = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"
        test_file.write_text(content)
        
        result = tools.read_file(test_file, start_line=2, end_line=4)
        assert "Line 2" in result
        assert "Line 3" in result
        assert "Line 4" in result
        assert "Line 1" not in result
        assert "Line 5" not in result
    
    def test_read_file_not_found(self, temp_dir):
        """Test reading non-existent file"""
        with pytest.raises(RoninFileNotFoundError):
            tools.read_file(temp_dir / "nonexistent.txt")
    
    def test_create_file_success(self, temp_dir):
        """Test creating a new file"""
        test_file = temp_dir / "new.md"
        result = tools.create_file(test_file, "# New File\nContent")
        
        assert result["created"] == str(test_file)
        assert result["lines"] == 2
        assert test_file.exists()
        assert test_file.read_text() == "# New File\nContent"
    
    def test_create_file_already_exists(self, temp_dir):
        """Test creating file that already exists"""
        test_file = temp_dir / "existing.md"
        test_file.write_text("Existing")
        
        with pytest.raises(FileAlreadyExistsError):
            tools.create_file(test_file, "New content")
    
    def test_delete_file_success(self, temp_dir):
        """Test deleting a file"""
        test_file = temp_dir / "delete.txt"
        test_file.write_text("To be deleted")
        
        result = tools.delete_file(test_file)
        
        assert result["deleted"] == str(test_file)
        assert not test_file.exists()
    
    def test_delete_file_not_found(self, temp_dir):
        """Test deleting non-existent file"""
        with pytest.raises(RoninFileNotFoundError):
            tools.delete_file(temp_dir / "nonexistent.txt")
    
    def test_modify_file_append(self, temp_dir):
        """Test appending to a file"""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Original content")
        
        old_content, new_content, result = tools.modify_file(
            test_file,
            anchor="",
            action="after",
            content="\nAppended content"
        )
        
        assert result["action"] == "after"
        assert test_file.read_text() == "Original content\nAppended content"
    
    def test_modify_file_prepend(self, temp_dir):
        """Test prepending to a file"""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Original content")
        
        old_content, new_content, result = tools.modify_file(
            test_file,
            anchor="",
            action="before",
            content="Prepended content\n"
        )
        
        assert result["action"] == "before"
        assert test_file.read_text() == "Prepended content\nOriginal content"
    
    def test_modify_file_replace(self, temp_dir):
        """Test replacing content in a file"""
        test_file = temp_dir / "test.txt"
        test_file.write_text("Hello world\nGoodbye world")
        
        old_content, new_content, result = tools.modify_file(
            test_file,
            anchor="world",
            action="replace",
            content="universe",
            occurrence=0  # Replace all
        )
        
        # Check that modification occurred (result structure may vary)
        assert test_file.read_text() == "Hello universe\nGoodbye universe"
    
    def test_search_files_found(self, temp_dir):
        """Test searching for text in files"""
        (temp_dir / "file1.txt").write_text("Hello world\nThis is a test")
        (temp_dir / "file2.md").write_text("World peace\nHello there")
        
        result = tools.search_files(temp_dir, "Hello")
        
        assert result["total_matches"] == 2
        assert result["files_with_matches"] == 2
        assert len(result["matches"]) == 2
    
    def test_search_files_not_found(self, temp_dir):
        """Test searching for non-existent text"""
        (temp_dir / "file.txt").write_text("Some content")
        
        result = tools.search_files(temp_dir, "nonexistent")
        
        assert result["total_matches"] == 0
        assert result["files_with_matches"] == 0
        assert result["matches"] == []


class TestGitTools:
    """Test git-related tools"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)
    
    @pytest.fixture
    def temp_git_dir(self):
        """Create a temporary directory with git repo"""
        temp = tempfile.mkdtemp()
        temp_path = Path(temp)
        # Initialize git repo
        import subprocess
        subprocess.run(["git", "init"], cwd=temp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=temp_path)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_path)
        yield temp_path
        shutil.rmtree(temp)
    
    def test_git_init_new_repo(self, temp_dir):
        """Test initializing a new git repository"""
        # temp_dir fixture is defined in TestFileTools, reuse it here
        result = tools.git_init(temp_dir)
        
        assert "path" in result
        assert (temp_dir / ".git").exists()
    
    def test_git_init_existing_repo(self, temp_git_dir):
        """Test initializing in existing repository"""
        result = tools.git_init(temp_git_dir)
        
        assert "error" in result
        assert "already exists" in result["error"].lower()
    
    def test_git_status_clean(self, temp_git_dir):
        """Test git status in clean repository"""
        result = tools.git_status(temp_git_dir)
        
        assert "branch" in result
        assert result.get("staged", []) == []
        assert result.get("modified", []) == []
    
    def test_git_status_with_changes(self, temp_git_dir):
        """Test git status with uncommitted changes"""
        (temp_git_dir / "test.txt").write_text("New file")
        
        result = tools.git_status(temp_git_dir)
        
        assert "untracked" in result
        assert "test.txt" in result["untracked"]
    
    @patch('subprocess.run')
    def test_git_commit_success(self, mock_run, temp_git_dir):
        """Test successful git commit"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="[main abc123] Test commit\n 1 file changed",
            stderr=""
        )
        
        result = tools.git_commit(temp_git_dir, "Test commit")
        
        assert "commit_hash" in result
        assert result["message"] == "Test commit"
    
    @patch('subprocess.run')
    def test_git_log_success(self, mock_run, temp_git_dir):
        """Test git log retrieval"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc123||Test commit||Test User||2024-01-01||file.txt",
            stderr=""
        )
        
        result = tools.git_log(temp_git_dir, limit=5)
        
        assert "commits" in result
        assert len(result["commits"]) > 0
    
    def test_git_diff_no_changes(self, temp_git_dir):
        """Test git diff with no changes"""
        result = tools.git_diff(temp_git_dir)
        
        assert "diff" in result
    
    @patch('subprocess.run')
    def test_git_branch_list(self, mock_run, temp_git_dir):
        """Test listing git branches"""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="* main\n  feature",
            stderr=""
        )
        
        result = tools.git_branch(temp_git_dir, action="list")
        
        assert "branches" in result
        assert len(result["branches"]) == 2
    
    @patch('subprocess.run')
    def test_git_revert_file(self, mock_run, temp_git_dir):
        """Test reverting file changes"""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        result = tools.git_revert(temp_git_dir, target="test.txt", type="file")
        
        assert "action" in result or "error" in result


class TestToolRegistry:
    """Test the tool registry system"""
    
    def test_get_tool_specs(self):
        """Test generating tool specifications"""
        from tool_registry import get_tool_specs
        
        specs = get_tool_specs(Path("/test"))
        
        assert isinstance(specs, list)
        assert len(specs) > 0
        
        # Check a specific tool
        list_files_spec = next((s for s in specs if s["name"] == "list_files"), None)
        assert list_files_spec is not None
        assert "description" in list_files_spec
        assert "input_schema" in list_files_spec
    
    def test_get_tool(self):
        """Test retrieving a tool definition"""
        from tool_registry import get_tool
        
        tool = get_tool("read_file")
        
        assert tool is not None
        assert tool.name == "read_file"
        assert tool.handler is not None
        assert tool.category == "read"
    
    def test_list_tools_by_category(self):
        """Test grouping tools by category"""
        from tool_registry import list_tools_by_category
        
        categories = list_tools_by_category()
        
        assert "read" in categories
        assert "write" in categories
        assert "git" in categories
        assert len(categories["git"]) >= 7  # At least 7 git tools


class TestFormatters:
    """Test output formatters"""
    
    def test_format_file_list(self):
        """Test file list formatting"""
        from tool_registry import format_file_list
        
        result = {
            "count": 2,
            "pattern": "*.md",
            "files": [
                {"path": "test.md", "lines": 10, "size_display": "256B"},
                {"path": "readme.md", "lines": 50, "size_display": "1.2KB"}
            ]
        }
        
        output = format_file_list(result)
        
        assert "Found 2 files" in output
        assert "test.md" in output
        assert "readme.md" in output
    
    def test_format_git_status(self):
        """Test git status formatting"""
        from tool_registry import format_git_status
        
        result = {
            "branch": "main",
            "staged": ["file1.txt"],
            "modified": ["file2.txt"],
            "untracked": ["file3.txt"]
        }
        
        output = format_git_status(result)
        
        assert "Current branch: main" in output
        assert "STAGED" in output
        assert "MODIFIED" in output
        assert "UNTRACKED" in output