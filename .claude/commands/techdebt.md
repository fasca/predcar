Scan the entire codebase for technical debt. Look for:

1. **Duplicated code**: Functions or blocks that appear in multiple places
2. **Missing tests**: Public functions without corresponding test coverage
3. **TODO/FIXME/HACK comments**: List them all with file and line number
4. **Missing type hints**: Functions without return type or parameter types
5. **Missing docstrings**: Public functions/classes without docstrings
6. **Bare exceptions**: Any `except:` or `except Exception:` without specific handling
7. **Hardcoded values**: Magic numbers or strings that should be in config.py
8. **Print statements**: Any `print()` that should be `logging`

Output a prioritized list with file references. Suggest fixes for the top 5 items.
