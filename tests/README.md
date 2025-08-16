# Ronin Test Suite

## Setup

Install the test dependencies:

```bash
pip install -e ".[test]"
```

Or for all development dependencies:

```bash
pip install -e ".[dev]"
```

## Running Tests

### Run all tests
```bash
pytest
```

### Run with coverage
```bash
pytest --cov=. --cov-report=html
```

### Run specific test categories
```bash
# Unit tests only
pytest tests/unit -m "not integration"

# Integration tests only  
pytest tests/integration -m integration

# Fast tests only (exclude slow tests)
pytest -m "not slow"
```

### Run specific test files
```bash
pytest tests/unit/test_tools.py
pytest tests/integration/test_chat_session.py
```

### Run with verbose output
```bash
pytest -v
```

### Run tests in parallel (faster)
```bash
pip install pytest-xdist
pytest -n auto
```

## Test Structure

```
tests/
├── unit/                  # Unit tests for individual components
│   ├── test_tools.py     # Test tool handlers
│   └── test_claude_api_mock.py  # Test API mocking
├── integration/          # Integration tests
│   └── test_chat_session.py  # Test ChatSession integration
└── fixtures/            # Test data and fixtures
```

## Writing Tests

### Test markers
- `@pytest.mark.unit` - Unit tests
- `@pytest.mark.integration` - Integration tests  
- `@pytest.mark.slow` - Slow tests (>1s)
- `@pytest.mark.mock` - Tests using mocks

### Example test
```python
import pytest
from pathlib import Path

@pytest.mark.unit
def test_example():
    assert True

@pytest.mark.integration
@pytest.mark.slow
def test_complex_workflow():
    # Complex test that takes time
    pass
```

## Coverage Reports

After running tests with coverage, view the HTML report:

```bash
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

## CI/CD

Tests run automatically on:
- Push to main or develop branches
- Pull requests to main
- Manual workflow dispatch

The CI pipeline tests on:
- Multiple Python versions (3.9-3.12)
- Multiple OS (Ubuntu, macOS, Windows)
- Includes linting, security checks, and package building

## Debugging Tests

### Run specific test with output
```bash
pytest tests/unit/test_tools.py::TestFileTools::test_list_files -v -s
```

### Run with debugger
```bash
pytest tests/unit/test_tools.py --pdb
```

### Show test durations
```bash
pytest --durations=10
```

## Common Issues

### Import errors
Make sure you've installed the package in editable mode:
```bash
pip install -e .
```

### Git tests failing
Configure git for testing:
```bash
git config --global user.email "test@test.com"
git config --global user.name "Test User"
```

### Permission errors
Some tests create temporary files. Ensure you have write permissions in the temp directory.