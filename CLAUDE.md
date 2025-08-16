# Claude Code Instructions for Ronin Project

## Important: Always Run Tests

When you complete implementing a new feature or making significant changes, you MUST:

1. **Run the test suite** to ensure nothing is broken:
   ```bash
   pytest tests/ -v
   ```

2. **Run linting** to ensure code quality:
   ```bash
   ruff check .
   ```

3. **Check test coverage** for new code:
   ```bash
   pytest --cov=. --cov-report=term-missing
   ```

## Project-Specific Guidelines

### Before Committing
- Always run tests: `pytest`
- Check for linting issues: `ruff check .`
- Ensure new features have corresponding tests
- Update documentation if needed

### Testing Commands
```bash
# Quick test run
pytest

# Verbose with coverage
pytest -v --cov=. --cov-report=term-missing

# Unit tests only (fast)
pytest tests/unit -m "not integration"

# Integration tests
pytest tests/integration -m integration

# Specific test file
pytest tests/unit/test_tools.py
```

### When Adding New Features
1. Write tests FIRST (TDD) or immediately after implementation
2. Ensure test coverage for new code is >80%
3. Add both unit and integration tests where applicable
4. Run the full test suite before marking feature as complete

### Git Workflow
1. Make changes
2. Run tests: `pytest`
3. Fix any failures
4. Run linting: `ruff check .`
5. Only then commit changes

### Tool Development
When adding new tools to `tools.py` and `tool_registry.py`:
1. Add the tool implementation in `tools.py`
2. Register it in `tool_registry.py` 
3. Add unit tests in `tests/unit/test_tools.py`
4. Add integration tests if needed
5. Run tests to verify

## Key Files to Remember

- `tool_registry.py` - Single source of truth for all tools
- `tools.py` - Tool implementation handlers
- `tests/unit/test_tools.py` - Unit tests for tools
- `tests/integration/test_chat_session.py` - Integration tests
- `pytest.ini` - Test configuration
- `.github/workflows/test.yml` - CI/CD pipeline

## Code Quality Standards

- All new code must have tests
- Test coverage should not decrease
- All tests must pass before considering a feature complete
- Follow existing code patterns and conventions

## Quick Checks

Before saying "I'm done" or "Feature complete", ask yourself:
- [ ] Did I **write new tests** for the feature?
- [ ] Did I run `pytest`?
- [ ] Did all tests pass?
- [ ] Did I verify my new tests actually test the feature?
- [ ] Did I check linting with `ruff`?
- [ ] Is the test coverage adequate (>80% for new code)?

Remember: **No feature is complete without tests! Always write tests for new features!**

## Test Writing Checklist for New Features

When implementing a new feature, you MUST:

1. **Write unit tests** in `tests/unit/` that test:
   - Normal operation (happy path)
   - Edge cases
   - Error conditions
   - Input validation

2. **Write integration tests** in `tests/integration/` if the feature:
   - Interacts with multiple components
   - Has complex workflows
   - Affects the ChatSession or Agent

3. **Verify tests actually test the feature**:
   ```bash
   # Run just your new tests to ensure they work
   pytest tests/unit/test_your_feature.py -v
   
   # Temporarily break your feature code and ensure tests fail
   # Then fix it and ensure tests pass
   ```

4. **Check coverage of your new code**:
   ```bash
   pytest --cov=your_module --cov-report=term-missing
   ```

## Example: Adding a New Tool

When adding a new tool called `example_tool`:

1. Implement in `tools.py`:
   ```python
   def example_tool(root: Path, param1: str) -> Dict:
       # Implementation
   ```

2. Register in `tool_registry.py`:
   ```python
   "example_tool": ToolDefinition(...)
   ```

3. **MUST ADD TESTS** in `tests/unit/test_tools.py`:
   ```python
   def test_example_tool_success(self, temp_dir):
       """Test example_tool normal operation"""
       result = tools.example_tool(temp_dir, "test")
       assert result["status"] == "success"
   
   def test_example_tool_error(self, temp_dir):
       """Test example_tool error handling"""
       with pytest.raises(ValueError):
           tools.example_tool(temp_dir, "invalid")
   ```

4. Run tests to verify:
   ```bash
   pytest tests/unit/test_tools.py::test_example_tool_success -v
   ```

Without tests, the feature is NOT complete!