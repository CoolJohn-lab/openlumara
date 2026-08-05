# Core: Functions and Utilities (`core.functions`)

The functions module provides utility functions used throughout the OpenLumara framework. These are imported into the core namespace via `core/__init__.py`.

## Overview

This module contains helper functions for:
- Logging
- Path handling and validation
- Error handling
- String manipulation
- Security utilities

## Functions

### `log(category, msg)`

Simple console logging function.

**Parameters:**
- `category` (str) - The log category
- `msg` (str) - The message to log

**Behavior:**
- If `core.manager.global_instance` exists: Uses the manager's logging (propagates to all channels)
- If no manager: Prints directly to terminal with `[CATEGORY]` prefix

**Use Case:** Used during early initialization before the manager is loaded.

**Warning:** Strictly for cases where the manager or channel instances cannot be accessed (e.g., during config loading).

### `detail_error(e)`

Provides detailed error information in a compact format.

**Parameters:**
- `e` (Exception) - The exception to format

**Returns:**
- String with error details

**Behavior:**
- If `core.debug` is False: Returns `str(e)` (just the error message)
- If `core.debug` is True: Returns formatted string with:
  - Exception message
  - Filename, function name, and line number
  - Full traceback

**Example Output:**
```
division by zero | config.py, _flatten_settings, ln:45
Traceback (most recent call last):
  File "config.py", line 45, in _flatten_settings
    return 1/0
ZeroDivisionError: division by zero
```

### `log_error(msg, e)`

Logs an error with full details.

**Parameters:**
- `msg` (str) - Error description
- `e` (Exception) - The exception

**Behavior:**
- If no manager: Prints `[ERROR]` with detail and full traceback to stdout
- If manager exists: Logs via `manager.log("error", ...)` with formatted traceback

**Use Case:** Similar to `log()` but for errors during early initialization.

### `get_path(path="", sandbox=True)`

Gets a path relative to the project root directory.

**Parameters:**
- `path` (str) - The relative path to resolve (default: empty = project root)
- `sandbox` (bool) - Whether to sandbox the path (default: True)

**Returns:**
- Absolute path string

**Behavior:**
1. Resolves the project root as `../` relative to this file's location
2. If path is absolute: Returns as-is
3. If path is relative and sandbox=True: Uses `sandbox_path()` to validate
4. If path is relative and sandbox=False: Joins with project root

**Example:**
```python
core.get_path()                    # Returns "/path/to/openlumara"
core.get_path("data")              # Returns "/path/to/openlumara/data"
core.get_path("data", sandbox=False) # Returns "/path/to/openlumara/data"
```

### `get_data_path(subpath=None)`

Gets the path to the data directory.

**Parameters:**
- `subpath` (str, optional) - Subpath within the data directory

**Returns:**
- Absolute path to the data directory (or subpath if provided)

**Behavior:**
1. Gets `data_folder` from config (default: "data")
2. If relative, resolves from project root using `get_path()`
3. Creates the directory if it doesn't exist
4. Appends subpath using `sandbox_path()` if provided

**Example:**
```python
core.get_data_path()           # Returns "/path/to/openlumara/data"
core.get_data_path("chats")    # Returns "/path/to/openlumara/data/chats"
```

### `remove_duplicates(lst)`

Removes duplicate items from a list while preserving order.

**Parameters:**
- `lst` (list) - The list to deduplicate

**Returns:**
- New list with duplicates removed

**Behavior:**
- Iterates through the list
- Adds items to a new list only if not already present
- Preserves the original order

### `validate_path_string(path)`

Validates a path string for traversal and encoding attacks.

**Parameters:**
- `path` (str) - The path to validate

**Returns:**
- Cleaned path string

**Behavior:**
1. Strips path separators from start/end
2. Decodes URL encoding up to 3 times (catches double/triple encoding)
3. Normalizes slashes to OS-specific separator
4. Strips again after decoding
5. Checks for `..` (traversal) and null bytes
6. Raises `ValueError` if any attack is detected

**Security:** Protects against:
- Directory traversal (`../../etc/passwd`)
- URL-encoded traversal (`%2e%2e%2f`)
- Null byte injection (`file.txt\x00.jpg`)

### `sandbox_path(base_path, requested_path=None)`

Protects against path traversal attacks by ensuring paths stay within a sandbox.

**Parameters:**
- `base_path` (str) - The allowed base directory
- `requested_path` (str, optional) - The path to validate (default: returns base_path)

**Returns:**
- Resolved, sanitized absolute path

**Behavior:**
1. If no requested_path: Returns base_path as-is
2. Normalizes slashes to OS separator
3. Strips leading/trailing separators
4. Removes base_path prefix if present (handles cases where AI/user includes it)
5. Validates the path string (calls `validate_path_string()`)
6. Checks for symlinks in any path component (raises `ValueError` if found)
7. Uses `os.path.realpath()` to resolve the final path
8. Checks if the resolved path starts with the base path
9. Case-insensitive comparison on Windows

**Security Features:**
- Prevents directory traversal (`..`)
- Blocks symlinks (can't escape sandbox via symlink)
- Handles URL-encoded attacks
- Case-insensitive on Windows

**Example:**
```python
core.sandbox_path("/data", "chats/abc.json")  # Returns "/data/chats/abc.json"
core.sandbox_path("/data", "../etc/passwd")   # Raises ValueError
core.sandbox_path("/data", "/data/chats/file") # Returns "/data/chats/file"
```

## Import Structure

These functions are imported in `core/__init__.py`:

```python
from core.functions import *
```

This makes them available as `core.log()`, `core.get_path()`, etc.

## Best Practices

1. **Use `core.log()` for early logging** - Before manager is loaded
2. **Use `manager.log()` for normal logging** - After initialization
3. **Always use `sandbox_path()` for file paths** - Never trust user input
4. **Check `core.debug` before detailed errors** - Avoid info leakage in production
5. **Handle `ValueError` from path functions** - User input may be malicious