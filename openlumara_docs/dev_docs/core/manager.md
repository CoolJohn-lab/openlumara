# Core: The Manager (`core.Manager`)

The `Manager` is the central nervous system of OpenLumara. It is responsible for the initialization, orchestration, and lifecycle management of the entire framework.

## Overview

The Manager is created once at startup and lives for the entire duration of the application. It coordinates all components: channels, modules, API connections, and tools.

## Responsibilities

### 1. Initialization and Startup
When the application starts, the `Manager` performs several critical tasks:
- **Config Loading**: Reads the configuration from `config.yml` (done by `core.config.load()` before Manager.run()).
- **Storage Initialization**: Initializes the `StorageDict` for persistent data (`save.msgpack`).
- **Channel Loading**: Identifies and instantiates all enabled channels from the `channels/` and `user_channels/` directories.
- **Module Loading**: Loads both core modules and user-defined modules from the `modules/` and `user_modules/` directories.
- **Auto-Installer**: Installs/uninstalls Python dependencies for enabled/disabled modules and channels (unless `--disable-auto-installer` is passed).
- **API Connection**: Attempts to establish a connection to the configured AI provider (non-fatal — continues in disconnected mode on failure).

### 2. Execution Modes
The `Manager` supports special execution modes via command-line arguments:
- **Pure Mode** (`--pure`): Disables all modules. No tools, no AI logic — just the channel.
- **Coder Mode** (`--coder`): Loads only the `coder` module, disabling all others.

### 3. Lifecycle Management
The `Manager` controls the execution flow:
- **The Main Loop**: Runs the asynchronous task loop (`asyncio.gather()`) that keeps all channels and background module tasks active.
- **Task Management**: Tracks all running asynchronous tasks in `self._async_tasks`. Each task has a done callback (`_remove_async_task`) for cleanup.
- **Shutdown**: Handles graceful shutdown with double-shutdown prevention (`_prevent_double_shutdown`). Calls `on_shutdown()` on all modules and channels, then cancels all async tasks.
- **Restart**: Sets `_restart_requested` flag, triggers shutdown, and returns `"restart"` from `run()`.

### 4. Orchestration
The `Manager` acts as the bridge between different components:
- **Module/Channel Bridge**: When a channel becomes active, the `Manager` ensures all modules have access to it via `_set_as_active_channel()`.
- **Tool Provisioning**: As modules are loaded, the `Manager` scans them for functions that should be exposed as tools to the AI (via `load_module_tools()`).
- **System Prompt Assembly**: The `Manager` coordinates with all active modules to build the complete system prompt used for AI requests, categorizing prompts into top/middle/bottom sections.

### 5. Logging
- **Broadcast Logging**: `log()` propagates messages to **all** channels via `on_log()`.
- **Error Logging**: `log_error()` includes full tracebacks in debug mode.
- **Log Buffer**: During early initialization (before channels are loaded), log messages are buffered in `core.modules.log_buffer` and drained once channels are ready via `_drain_log_buffers()`.

## Key Methods

### Lifecycle
| Method | Description |
| :--- | :--- |
| `run()` | The main entry point that starts the entire system. Loads channels, modules, connects API, and runs the async loop. Returns `"restart"` if restart was requested, `None` otherwise. |
| `shutdown()` | Gracefully stops all channels, modules, and background tasks. Double-shutdown safe. |
| `restart()` | Triggers a full system restart by setting `_restart_requested` flag and calling shutdown. |

### Module/Channel Management
| Method | Description |
| :--- | :--- |
| `toggle_module(module_name, autorestart=True)` | Enables or disables a module at runtime. Modifies config and auto-restarts if requested. |
| `toggle_channel(channel_name, autorestart=True)` | Enables or disables a channel at runtime. Modifies config and auto-restarts if requested. |
| `reload_module(module_name)` | Reloads a specific module: unloads tools → runs `on_shutdown()` → runs `on_ready()` → reloads tools. |
| `add_module_class(module, is_user_module=False)` | Instantiates a module class and returns it. Handles pure/coder mode checks. |
| `load_module_tools(module)` | Scans a module for callable methods and registers them as AI tools. |
| `unload_module_tools(module)` | Removes all tools belonging to a module from the manager's tool list. |

### Prompt Assembly
| Method | Description |
| :--- | :--- |
| `get_system_prompt()` | Aggregates system prompt fragments from all active modules, categorized into top/middle/bottom sections. Respects `disabled_prompts` config and character module overrides. |
| `get_end_prompt(prevent_recursion=False)` | Aggregates end prompt fragments from all active modules. Prevents recursion for `token_threshold` module. |
| `get_settings_structure()` | Returns the settings structure for all loaded modules (for WebUI settings editor). |

### Tool Management
| Method | Description |
| :--- | :--- |
| `parse_tool_docstring(docstring)` | Parses Google-style docstrings to extract parameter descriptions and returns a cleaned docstring (without Args/Returns sections). |

### Logging
| Method | Description |
| :--- | :--- |
| `log(category, message)` | Propagates messages to **all** channels via `on_log()`. |
| `log_error(message, e)` | Propagates error messages with exception to all channels. |
| `_drain_log_buffers()` | Drains the log buffer from early initialization to all channels. |

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `API` | `APIClient` | The API client instance (connected later via `API.connect()`). |
| `savedata` | `StorageDict` | Persistent storage for app-wide data (`save.msgpack`). |
| `channels` | `dict` | Dictionary of all loaded channel instances, keyed by name. |
| `channel` | `Channel \| None` | The currently active channel (dynamically switched). |
| `modules` | `dict` | Dictionary of all loaded module instances, keyed by name. |
| `user_modules` | `dict` | Dictionary of user module instances, keyed by name. |
| `broken_modules` | `list` | Tracks module names that threw errors during prompt generation (skipped in future). |
| `tools` | `list` | List of all registered tool definitions (JSON schema objects). |
| `tool_names` | `list` | List of all registered tool names (strings). |
| `args` | `Namespace` | Command-line arguments passed at startup. |
| `_async_tasks` | `set` | Set of all running async tasks (channels, background modules, etc.). |
| `pure_mode` | `bool` | If True, disables all modules. |
| `coding_mode` | `bool` | If True, loads only the `coder` module. |
| `_restart_requested` | `bool` | Flag set when restart is requested. |
| `_prevent_double_shutdown` | `bool` | Prevents shutdown from running twice. |

## System Prompt Categorization

The `get_system_prompt()` method categorizes module prompts into three sections:
- **Top**: `agent_framework_awareness`, `identity`, `memory`, `writing_style`
- **Bottom**: `time`, `system`
- **Middle**: All other modules

**Special handling:**
- Modules in `config.modules.disabled_prompts` are skipped
- If a character is active and `disable_agent_prompts_when_character_active` is True, only the character prompt is shown (except for `characters` and `writing_style`)
- If tools are disabled, only modules in `core.modules.nonagentic` (`characters`, `writing_style`, `time`) have their prompts inserted
- Modules can override their header via a `header` class attribute

**Prompt format:**
```
# HeaderName
Prompt content from module
```

## Tool Registration Flow

1. `load_module_tools()` iterates over all public methods of a module class (from `type(module).__dict__`)
2. Skips methods starting with `_`, `result`, or `on_*`
3. Skips methods decorated with `@core.module.command`
4. Parses the docstring for parameter descriptions (Google-style)
5. Inspects the function signature to determine parameter types:
   - `str` → `string`
   - `int` → `integer`
   - `bool` → `boolean`
   - `list` → `array`
   - `dict` → `object`
   - Empty annotation → `string`
6. Builds a JSON schema tool object with `strict: true`
7. Appends to `self.tools` and `self.tool_names`

**Tool object structure:**
```python
{
    "type": "function",
    "function": {
        "name": "module_name_method_name",
        "description": "Docstring text",
        "parameters": {
            "type": "object",
            "properties": {
                "arg1": {"type": "string", "description": "..."},
                "arg2": {"type": "integer"}
            },
            "required": ["arg1"],
            "additionalProperties": False
        },
        "strict": True
    }
}
```

## Global Instance

The `Manager` exposes a global instance via `core.manager.global_instance`, allowing early-stage code (e.g., during config loading) to access the manager for logging before it's fully initialized.

## Internal Workflow (Startup)

1.  `Manager.__init__(cmdline_args)` is called — creates API client, initializes dicts
2.  `Manager.run()` is invoked
3.  Loads enabled channels from config, installs dependencies, instantiates each channel, calls `init()` and `on_ready()`
4.  Loads enabled user channels (same process)
5.  Sets `global_instance = self`
6.  Drains any early log buffers
7.  Loads enabled core modules, runs `_start()` (which calls `on_ready()` and optionally `on_background()`), registers tools
8.  Loads enabled user modules (same process)
9.  Uninstalls dependencies for disabled modules/channels
10. Attempts API connection (non-fatal)
11. Starts each channel's `run()` task and `_start_push_queue()` task
12. Enters `asyncio.gather()` main loop
13. On exit (KeyboardInterrupt, CancelledError, or exception), calls `shutdown()`
14. Returns `"restart"` if `_restart_requested` was set, else `None`

## Internal Workflow (Shutdown)

1.  Sets `_prevent_double_shutdown = True`
2.  Logs "Shutting down.."
3.  Calls `on_shutdown()` on all modules (handles sync/async)
4.  Calls `_shutdown()` then `on_shutdown()` on all channels
5.  Sets `global_instance = None`
6.  Cancels all tasks in `_async_tasks`
7.  Awaits each cancelled task
8.  Sleeps 1 second for cleanup
9.  Logs "Shutdown complete"
