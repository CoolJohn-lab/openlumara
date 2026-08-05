# Core: Messages System (`core.messages`)

The `Messages` class handles individual message storage and retrieval within a single chat session. Messages are stored in separate JSON files per chat, allowing efficient access and management.

## Overview

Each chat has its own messages file stored at:
```
data/chats/<channel_name>/history/<chat_id>.json
```

The Messages class provides methods to add, edit, delete, and retrieve messages from a chat's history.

## Class: `Messages`

### Initialization

```python
Messages(channel, chat)
```

**Parameters:**
- `channel` - The Channel instance
- `chat` - The Chat instance that owns these messages

**What happens:**
1. Validates that the chat has a string ID
2. Constructs the path to the chat's history file
3. Initializes a `StorageList` for the messages
4. Loads existing messages from disk

**Note:** If the chat ID is not a string, an exception is raised.

### Methods

#### `async save()`
Saves messages to disk and updates the chat's timestamp.

**Behavior:**
- Calls `chat.update_timestamp()` to update the last-modified time
- Calls `data.save()` to persist the messages

**Returns:**
- Result of the save operation

#### `async get(index=None)`
Retrieves messages from the chat history.

**Parameters:**
- `index` (int, optional) - If provided, returns only the message at that index

**Returns:**
- If `index` is provided: The message dict at that index (raises `Exception` if invalid)
- If `index` is None: The entire message history list

#### `async add(message, cmd=False, ghost=False)`
Adds a new message to the chat history.

**Parameters:**
- `message` (dict) - The message to add (must have "role" and optionally "content")
- `cmd` (bool) - Whether this is a command message
- `ghost` (bool) - Whether this message should be invisible to the AI

**Behavior:**
1. Makes a copy of the message to avoid modifying the original
2. Ensures `_metadata` dict exists
3. Auto-generates chat title from first user message (if title is "New chat")
4. Sets ghost flag if requested
5. Marks command messages with `is_cmd` metadata
6. Runs `on_message_inject()` hooks on all modules to add timestamps, etc.
7. Appends to the messages list
8. Saves and updates timestamp

**Returns:**
- `True` on success

**Message Metadata:**
- `_metadata.ghost` - Set to True for ghost messages (invisible to AI)
- `_metadata.is_cmd` - Set to True for command messages
- `_metadata.injection` - Set by `on_message_inject()` hooks (e.g., timestamps)

#### `async edit(index, message)`
Edits a message at the specified index.

**Parameters:**
- `index` (int) - The index of the message to edit
- `message` (dict) - The new message content

**Returns:**
- `True` on success
- `False` if index is out of bounds

#### `async delete(index)`
Deletes a message at the specified index.

**Parameters:**
- `index` (int) - The index of the message to delete

**Returns:**
- The new last index after deletion

#### `async delete_from(index)`
Deletes the message at the given index and all messages after it.

**Parameters:**
- `index` (int) - The index to delete from (inclusive)

**Behavior:**
- Keeps all messages before the target index
- Loads the truncated list back into storage

**Returns:**
- `True` on success
- Raises `Exception` if index is out of bounds

#### `async clear()`
Clears all messages from the chat.

**Returns:**
- `True` on success

#### `async get_last_message_with_role(role, cutoff_index=None)`
Gets the latest message with a specified role.

**Parameters:**
- `role` (str) - The message role to search for ("user", "assistant", etc.)
- `cutoff_index` (int, optional) - If provided, searches backwards from this index

**Returns:**
- The index of the last message with the given role
- `-1` if no matching message is found

**Use Case:** Useful for regenerating responses by targeting the last user message before a cutoff point.

## Message Structure

Messages follow the OpenAI message format:

```python
{
    "role": "user",           # "user", "assistant", "tool", "system"
    "content": "Message text", # String or list of content parts
    "tool_calls": [...],      # Present for assistant messages with tool calls
    "tool_call_id": "...",    # Present for tool messages
    "_metadata": {
        "ghost": False,       # Invisible to AI
        "is_cmd": False,      # Is a command
        "injection": "..."    # Injected content (e.g., timestamps)
    }
}
```

## Auto-Title Generation

When a new chat receives its first user message (that isn't a command), the chat title is automatically generated from the message content:
- First 100 characters + ".." if longer than 100 chars
- Media uploads don't trigger auto-title (avoids setting filename as title)

## Module Hooks

### `on_message_inject()`
Modules can implement `on_message_inject()` to inject content into user messages. The injected content is stored in `_metadata.injection` and later processed by `Context.get()` to append it to user messages.

**Common Use Case:** Adding timestamps to messages so the AI knows when each message was sent.

```python
# In a module:
async def on_message_inject(self):
    import datetime
    return f"[Sent at: {datetime.datetime.now().strftime('%H:%M')}]"
```

## Best Practices

1. **Always use `async add()`** - Don't append directly to the list (misses hooks and saves)
2. **Check `self.current` in Chat** - Messages belong to a specific chat
3. **Use `ghost=True` for system messages** - Prevents AI from seeing internal framework messages
4. **Handle exceptions in hooks** - Module `on_message_inject()` errors are caught and logged
5. **Respect message limits** - Context.py handles trimming, not Messages