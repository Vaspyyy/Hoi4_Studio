# Contributing to HOI4 Modding Studio

Thank you for your interest in contributing to the HOI4 Modding Studio! This document outlines the guidelines and procedures for contributing to the project.

## Code of Conduct

By participating in this project, you agree to abide by our Code of Conduct. We expect all contributors to be respectful, professional, and considerate of others' time and effort.

## How to Contribute

### Reporting Issues

- Search existing issues before creating a new one
- Provide detailed steps to reproduce bugs
- Describe the expected vs. actual behavior
- Include system information (OS, Python version, etc.) when relevant
- Use appropriate labels when creating issues

### Submitting Changes

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes following the coding standards below
4. Write tests if applicable
5. Commit your changes with a clear, descriptive commit message
6. Push to your fork
7. Submit a pull request to the `main` branch

## Development Setup

1. Clone your fork of the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the environment: `source venv/bin/activate` (Linux/Mac) or `venv\Scripts\activate` (Windows)
4. Install dependencies: `pip install -r requirements.txt`
5. Run the application: `python -m src.main`

## Coding Standards

### Python Style Guide

- Follow PEP 8 style guidelines
- Use 4 spaces for indentation (no tabs)
- Maximum line length of 100 characters
- Use meaningful variable and function names
- Write docstrings for all public classes, methods, and functions
- Prefer f-strings for string formatting

### Type Hints

All functions and methods must include proper type hints:

```python
def example_function(param1: str, param2: int) -> bool:
    """Example function with type hints."""
    return True
```

### Commit Messages

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit first line to 72 characters or less
- Reference issues and pull requests after a blank line

Example:
```
Add validation for country tags

Validate that country tags are 3 characters and don't conflict with vanilla tags.
Fixes #123
```

## Pull Request Requirements

### Before Submitting

- Your code must pass all existing tests
- Add new tests for any new functionality
- Update documentation if applicable
- Ensure your code follows the style guidelines
- Squash commits if necessary to create a clean history
- Update the README if new features are added

### Review Process

- All pull requests must be reviewed by at least one maintainer
- Address all review comments before merging
- Maintainers may request changes to improve code quality
- Large changes should be discussed in an issue first

## Testing

### Running Tests

Execute the test suite:
```bash
python -m pytest tests/
```

### Adding Tests

- Write unit tests for new functionality
- Ensure test coverage doesn't decrease significantly
- Test edge cases and error conditions
- Keep tests focused and fast

## Documentation

- Update docstrings when modifying code
- Add examples where helpful
- Keep README.md up-to-date with new features
- Document breaking changes clearly

## Security

- Report security vulnerabilities responsibly through GitHub's private vulnerability reporting
- Don't introduce dependencies without justification
- Validate all user inputs
- Follow secure coding practices

## What We Won't Accept

- Code that doesn't follow the style guidelines
- Pull requests with failing tests
- Features that break backward compatibility without good reason
- Code without proper documentation
- Changes that don't include tests where applicable
- Large refactoring without prior discussion

## Getting Help

- Open an issue for questions about the codebase
- Discuss major changes in an issue before implementing
- Be patient during the review process

## Recognition

Contributors will be acknowledged in the project's README. Significant contributions may lead to collaborator status.

---

By contributing to this project, you agree that your contributions will be licensed under the project's license.