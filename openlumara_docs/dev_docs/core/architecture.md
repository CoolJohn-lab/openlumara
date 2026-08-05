# OpenLumara Core Architecture

This document provides an overview of OpenLumara's core architecture and how the main components interact with each other.

## High-Level Architecture

OpenLumara is built around a modular, event-driven architecture centered on the **Manager** class. The system consists of several key components that work together to provide an AI-powered assistant with extensive capabilities.

### Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Manager                              │
│  (Central orchestration: modules, channels, API, tools)      │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌──────────────┐  ┌───────────────┐
│    Channel    │  │   Modules    │  │   API Client  │
│  (User Inter- │  │ (Plugins/    │  │ (LLM Inter-   │
│   face)       │  │  Extensions) │  │   action)     │
└───────┬───────┘  └──────┬───────┘  └───────┬───────┘
        │                 │                  │
        ▼                 ▼                  ▼
┌───────────────┐  ┌──────────────┐  ┌───────────────┐
│   Context     │  │   ToolCalls  │  │   Storage     │
│ (Conversation │  │ (Function    │  │ (Data         │
│  History)     │  │  Execution)  │  │  Persistence) │
└───────────────┘  └──────────────┘  └───────────────┘
```

## Core Components

### 1. Manager (`manager.py`)
The central orchestration class that manages the entire framework lifecycle.

**Responsibilities:**
- Initializes and manages all channels and modules
- Handles the main event loop via asyncio
- Manages tool registration from modules
- Generates system prompts from active modules
- Handles graceful shutdown and restart
- Provides logging infrastructure to all channels

**Key Methods:**
- `run()` - Main entry point, starts all channels and begins the event loop
- `shutdown()` - Gracefully shuts down all components
- `get_system_prompt()` - Assembles system prompts from all active modules
- `load_module_tools()` - Dynamically registers module methods as AI tools

### 2. Channel (`channel.py`)
Base class for all user interface channels (CLI, WebUI, Discord, Telegram, etc.)

**Responsibilities:**
- Handles user input and displays responses
- Manages the push queue for unsolicited messages
- Processes multimodal content (images, audio, PDFs)
- Groups streamed tokens into displayable turns
- Routes commands to the command processor

**Key Features:**
- **Push Queue:** Allows modules to send messages without user prompting
- **Multimodal Support:** Handles images, audio, and PDF files
- **Stream Grouping:** Groups streamed tokens into logical turns for display
- **Command Processing:** Routes `/commands` to appropriate handlers

### 3. Context (`context.py`)
Manages the conversation context window sent to the AI model.

**Responsibilities:**
- Builds the complete context (system prompt + history + end prompt)
- Trims context to fit within token limits using binary search
- Handles summarization cutoff points
- Enforces message turn order (user/assistant/tool)
- Strips multimodal data from older messages to save tokens

**Key Features:**
- **Automatic Trimming:** Uses binary search to efficiently find optimal trim point
- **Agentic Loop Tracking:** Removes old reasoning to save context space
- **Turn Order Enforcement:** Ensures valid message sequences
- **Token Estimation:** Approximates token usage for context management

### 4. Chat (`chat.py`)
Manages chat history storage and retrieval.

**Responsibilities:**
- Stores chat metadata (title, category, tags, timestamps)
- Handles chat creation, deletion, loading, and switching
- Provides search functionality across all chats
- Exports chat history to readable format

**Storage Format:**
- Index file (msgpack): Chat metadata for all chats in a channel
- History files (JSON): Individual message history per chat

### 5. Messages (`messages.py`)
Handles individual message storage within a chat.

**Responsibilities:**
- Adds, edits, deletes, and retrieves messages
- Auto-generates chat titles from first user message
- Manages message metadata (ghost messages, command flags)
- Supports message injection hooks

### 6. ToolCalls (`toolcalls.py`)
Manages the execution of AI tool calls.

**Responsibilities:**
- Parses and repairs malformed JSON in tool arguments
- Routes tool calls to appropriate module methods
- Executes tools with timeout protection
- Handles recursive tool calling (agentic loops)
- Yields streaming updates during tool execution

**Key Features:**
- **JSON Repair:** Automatically fixes common JSON formatting issues
- **Timeout Protection:** Prevents tools from hanging indefinitely
- **Recursive Execution:** Supports chains of tool calls
- **Streaming Display:** Shows tool arguments as they're received

### 7. Turns (`turns.py`)
Groups messages into logical "turns" for display.

**Responsibilities:**
- Groups assistant messages (reasoning, content, tool calls) into turns
- Supports both history grouping and streaming grouping
- Merges tool responses with their corresponding tool calls

**Turn Structure:**
```python
{
    "role": "assistant",
    "messages": [
        {"type": "reasoning", "reasoning_content": "..."},
        {"type": "content", "content": "..."},
        {"type": "tool_calls", "tool_calls": [...]},
        {"type": "tool_response", "content": "..."}
    ]
}
```

### 8. Storage (`storage.py`)
Provides persistent storage abstractions.

**Classes:**
- `StorageList` - Subclassed list with file persistence (supports JSON, YAML, msgpack, text)
- `StorageDict` - Subclassed dict with file persistence
- `StorageText` - Simple text file storage

**Features:**
- Multiple format support (JSON, YAML, msgpack, text)
- Modification time caching to avoid unnecessary reloads
- Automatic directory creation
- Sandbox path protection

### 9. Config (`config.py`)
Manages configuration loading, validation, and schema generation.

**Responsibilities:**
- Loads and validates configuration from YAML files
- Manages module/channel discovery and loading
- Generates dynamic settings schemas for the UI
- Syncs config structure with available modules

**Key Features:**
- **Schema Validation:** Ensures config matches expected structure
- **Dynamic Discovery:** Automatically discovers available modules/channels
- **Cache System:** Caches module schemas with checksums for change detection
- **Reconciliation:** Automatically updates enabled/disabled lists

### 10. Commands (`commands.py`)
Handles command parsing and execution.

**Responsibilities:**
- Parses commands from user input
- Provides built-in commands (help, new, clear, status, etc.)
- Routes module-specific commands
- Handles configuration inspection and modification

**Command Format:** `/command [args]`
- Prefix configurable (default: `/`)
- Support for nested config paths: `/config api url http://localhost:5001/v1`

### 11. API Client (`api.py`)
Wraps the OpenAI-compatible API interface.

**Responsibilities:**
- Connects to the AI backend (local or cloud)
- Sends requests and handles streaming responses
- Manages authentication and error handling
- Supports reasoning/thinking features

**Supported Features:**
- Streaming responses with real-time token display
- Tool/function calling
- Reasoning content (Chain of Thought)
- Custom request fields
- Prompt warmup (speculative caching)

### 12. Modules (`modules.py`) & Module Base (`module.py`)
Framework for extensible plugins.

**Module Lifecycle:**
1. `__init__()` - Initialize module instance
2. `on_ready()` - Module initialization (config loading, setup)
3. `on_background()` - Start background tasks
4. `on_system_prompt()` - Provide system prompt content
5. `on_end_prompt()` - Provide end-of-context prompt
6. `on_message_inject()` - Inject data into user messages
7. `on_user_message()` - Hook for user messages
8. `on_assistant_message()` - Hook for assistant messages
9. `on_shutdown()` - Cleanup on shutdown

**Tool Registration:**
Any public method in a module class (not starting with `_` or `on_`) automatically becomes an AI tool. Method signatures and docstrings are used to generate the tool schema.

**Command Decorator:**
```python
@core.module.command("my_command", help="Description here")
async def my_command(self, arg1: str):
    """Optional detailed docstring"""
    return self.result("Success!")
```

## Data Flow

### User Message Flow
```
User Input
    │
    ▼
Channel.receive()
    │
    ├── Is command? → Commands.process_input()
    │       │
    │       ▼
    │   Execute command → Return response
    │
    └── Not command
            │
            ▼
    Module.on_user_message() hooks
            │
            ▼
    Context.add_message(user_message)
            │
            ▼
    API.send(context)
            │
            ▼
    Stream response → Group into turns → Display
            │
            ▼
    Context.add_message(assistant_message)
            │
            ▼
    Module.on_assistant_message() hooks
```

### Tool Call Flow
```
AI Response with tool_calls
    │
    ▼
ToolCallManager.process()
    │
    ├── Add assistant message to context
    │
    ├── For each tool call:
    │       │
    │       ├── Locate module and method
    │       │
    │       ├── Execute with timeout
    │       │
    │       └── Add tool response to context
    │
    ▼
Recursive call to AI with tools + history
    │
    ▼
[Repeat until no more tool calls]
    │
    ▼
Return final response to channel
```

## Error Handling

- **Exceptions:** Custom exceptions (`DependencyMissing`, `UnauthorizedException`) for specific error types
- **Logging:** Centralized logging through Manager, propagated to all channels
- **Broken Modules:** Modules that throw errors are added to `broken_modules` list and skipped
- **Timeout Protection:** Tools have configurable timeouts to prevent hanging
- **Graceful Degradation:** Framework continues operating even if individual components fail

## Security Features

- **Sandboxed Paths:** All file operations use sandbox path validation to prevent directory traversal
- **Command Authorization:** Admin commands require authorization flags
- **Timeout Limits:** Prevents tools from hanging indefinitely
- **Input Validation:** Commands and file paths are validated and sanitized

## Extension Points

1. **Custom Channels:** Create new UI channels by extending `Channel` base class
2. **Custom Modules:** Add functionality by extending `Module` base class
3. **Custom Storage Formats:** Extend `StorageList`/`StorageDict` with new formats
4. **API Backends:** Any OpenAI-compatible API is supported
5. **Tool Registration:** Automatic from module methods
6. **Command Registration:** Via `@command` decorator

## Startup Sequence

1. Load configuration from `config.yml`
2. Discover available modules and channels
3. Initialize and load enabled modules
4. Initialize and load enabled channels
5. Connect to AI API
6. Start channel event loops
7. Begin main asyncio event loop

## Shutdown Sequence

1. Signal all channels to stop
2. Call `on_shutdown()` on all modules
3. Call `_shutdown()` and `on_shutdown()` on all channels
4. Cancel all async tasks
5. Close HTTP connections
6. Save final state