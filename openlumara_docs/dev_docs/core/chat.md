# Core: The Chat System (`core.Chat`)

The `Chat` class manages chat history, metadata, and retrieval within OpenLumara. Each channel has its own set of chats, stored in channel-specific directories.

## Overview

The `Chat` class provides a complete chat management system including:
- Chat creation and auto-resume
- Message history storage and retrieval (stored separately per chat)
- Chat search across all conversations
- Chat metadata management (title, category, tags)
- Chat export functionality
- Automatic migration from legacy formats

## Storage Structure

### Directory Layout
```
data/
└── chats/
    └── <channel_name>/
        ├── index.mp          # MessagePack index file (chat metadata)
        ├── current           # File containing index of active chat
        └── history/
            ├── <chat_id>.json   # Chat history file
            ├── <chat_id2>.json
            └── ...
```

### Index File Format (msgpack)
Each entry in the index is a dictionary:
```python
{
    "id": "abc12345",           # 8-character ULID-based identifier
    "title": "New chat",        # Auto-generated from first message
    "category": "general",      # Chat category for organization
    "tags": [],                 # User-assigned tags
    "token_usage": 1234,        # Estimated token count
    "metadata": {},             # Custom metadata dictionary
    "created": "2024-01-01T00:00:00",  # ISO timestamp
    "updated": "2024-01-01T12:00:00"   # ISO timestamp
}
```

### History File Format (JSON)
Contains the raw message array:
```python
[
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there!"},
    ...
]
```

## Class: `Chat`

### Initialization

```python
Chat(channel)
```

**Parameters:**
- `channel` - The Channel instance that owns this chat

**What happens:**
1. Sets up the storage path for chats of this channel
2. Checks for legacy format files and prompts for migration
3. Initializes the index storage (msgpack format)
4. Sets up the current chat tracker file

### Methods

#### `async autoload()`
Automatically loads the last used chat or creates a new one.

**Behavior:**
- Checks if `auto_resume_chats` is enabled in config
- Reads the `current` file to find the last active chat index
- Loads that chat if it exists, otherwise creates a new chat
- This is the primary constructor for the Chat class

#### `async new(category="general", title="New chat", metadata=None)`
Creates a new chat.

**Parameters:**
- `category` (str) - Category to organize the chat under (default: "general")
- `title` (str) - Initial title (default: "New chat")
- `metadata` (dict) - Custom metadata to store with the chat

**Returns:**
- The new chat's ID (8-character string)

**Behavior:**
- Generates a new ULID-based ID
- Sets creation and update timestamps
- Initializes token usage count from current context
- Sets this chat as the current chat
- Saves the index

#### `async clear()`
Clears the current chat's message history.

**Behavior:**
- Clears all messages via the Messages class
- Resets token usage to 0
- Updates the chat timestamp
- Starts a prompt warmup (commented out in current code)

**Returns:**
- `True` on success

#### `async delete(id)`
Deletes a chat by its ID.

**Parameters:**
- `id` (str) - The chat ID to delete

**Returns:**
- The index of the newly active chat, or `False` if chat not found

**Behavior:**
- Removes the history file from disk
- Removes the entry from the index
- Adjusts the current chat index if needed
  - If the deleted chat was current, loads the next available chat
  - If no chats remain, auto-creates a new one

#### `async save()`
Saves the current chat's metadata to the index file.

**Note:** If no chat is currently loaded, this calls `new()` to create one.

#### `async load(id)`
Loads a chat by its ID.

**Parameters:**
- `id` (str) - The chat ID to load

**Returns:**
- `True` if a different chat was loaded
- `False` if the same chat was already active
- Raises `Exception` if chat ID is invalid

#### `async export()`
Exports the current chat history to a human-readable format.

**Returns:**
- A formatted string containing the chat history in a turn-based format

**Format:**
```
--- user ---
Hello!

--- assistant ---
Hi there! How can I help?
```

Tool calls are displayed with their arguments, and content is grouped by type.

#### `get(key=None, default=None, index=None)`
Retrieves metadata from the current chat.

**Parameters:**
- `key` (str, optional) - The metadata key to retrieve
- `default` - Default value if key doesn't exist
- `index` (int, optional) - Retrieve from a specific chat index

**Returns:**
- If `key` is `None`: returns the entire chat metadata dict
- If `key` is provided: returns the value for that key, or `default`

#### `async search(query, max_results=100)`
Searches across all chats for messages matching a query.

**Parameters:**
- `query` (str) - Search query (case-insensitive)
- `max_results` (int) - Maximum number of results to return

**Returns:**
- List of chat metadata dicts with search results, including:
  - `title_match` (bool) - Whether the query matched the title
  - `messages_found` (int) - Number of matching messages
  - `message_snippets` (list) - Snippets around each match

**Behavior:**
- Searches both chat titles and message content
- Generates context snippets (50 characters before/after match)
- Sorts results: title matches first, then by most recent
- Handles multimodal content by extracting text parts

#### `async set(key, value, index=None)`
Sets a metadata value on the current chat.

**Parameters:**
- `key` (str) - The metadata key
- `value` - The value to set
- `index` (int, optional) - Set on a specific chat index

**Returns:**
- `True` on success
- Raises `Exception` if key is not a valid chat property

#### `get_all()`
Returns all chats sorted by update time.

**Returns:**
- List of chat metadata dicts, sorted by `updated` field (most recent first)

#### `get_categories()`
Returns all unique categories used across chats.

**Returns:**
- List of category strings

## Migration System

OpenLumara includes an automatic migration system for upgrading from older chat formats.

### Legacy Format
Old versions stored chats in a single JSON file per channel:
```
data/<channel_name>_chats.json
```

### Migration Process
1. Detected on Chat initialization
2. Shows a warning with backup instructions
3. Waits for user to type `MIGRATE` in caps
4. Creates new directory structure
5. Migrates each chat's messages to individual JSON files
6. Creates new msgpack index
7. Backs up old files to `chat_migration_backups/`

**Safety:** Always creates a backup before migrating. Users are instructed to make their own backup first.

## Chat ID Generation

Chat IDs are generated using truncated ULIDs (Unique Locally-Identifiable Identifiers):
```python
new_id = str(ulid.ULID())[-8:]
```

The last 8 characters are used to keep IDs short while maintaining reasonable uniqueness. The code notes that truncation can theoretically lead to collisions, but this is rare in practice.

## Token Usage Tracking

Each chat tracks its estimated token usage:
- Set on chat creation from current context token count
- Updated when token usage is received from the API
- Used for context window management and display in status commands
- Stripped multimodal content is removed from older messages to save tokens

## Best Practices

1. **Always check `self.current` before operations** - Many methods require an active chat
2. **Use `async load()` instead of manual index manipulation** - Ensures proper state
3. **Handle migration warnings seriously** - Always backup before migrating
4. **Use `get_categories()` for UI organization** - Returns all available categories
5. **Respect the `max_results` limit in search** - Prevents excessive memory usage
