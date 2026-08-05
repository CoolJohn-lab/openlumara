# Core: Turns System (`core.turns`)

The `TurnCollector` class groups messages into logical "turns" for display. A turn represents a complete interaction cycle: a user message followed by the assistant's response (which may include reasoning, content, tool calls, and tool responses).

## Overview

Turns provide a way to display conversation history in a user-friendly format. Instead of showing raw messages, turns group related messages together:

```
User: "What's the weather?"

Assistant Turn:
  - Reasoning: "I should search for weather..."
  - Content: "Let me check that for you."
  - Tool Call: weather_search(city="Amsterdam")
  - Tool Response: {"temp": 22, "condition": "sunny"}
  - Content: "It's 22°C and sunny in Amsterdam!"
```

This works for both chat history (`group_history`) and streaming responses (`group_stream`).

## Class: `TurnCollector`

### Methods

#### `async group_history(history)`
Groups all finalized messages from history into turns.

**Parameters:**
- `history` (list) - List of message dicts from the chat

**Returns:**
- List of turn dicts

**Turn Structure:**
```python
{
    "role": "user",              # or "assistant"
    "messages": [msg1, msg2],    # List of messages in this turn
    "first_message_index": 0,    # Index of first message in original history
    "last_message_index": 3      # Index of last message (assistant turns only)
}
```

**Behavior:**
1. Iterates through messages in order
2. When a user message is encountered:
   - Finalizes any current assistant turn
   - Creates a new user turn with that single message
3. For assistant/tool messages:
   - Creates an assistant turn if one doesn't exist
   - Appends the message to the current turn
4. After the loop, finalizes any remaining assistant turn
5. Merges tool responses with their corresponding tool calls:
   - Builds a response map from tool messages
   - Adds `response` field to each tool call with matching `tool_call_id`

**Important:** Each message gets an `"index"` field added, allowing direct targeting of messages within turns.

#### `async group_stream(stream_generator)`
Processes a stream generator and yields progressively built turn objects.

**Parameters:**
- `stream_generator` - Async generator yielding token dicts from `API.send_stream()`

**Yields:**
- Token dicts (for non-display tokens like `prompt_progress`, `token_usage`)
- Turn dicts with type `"turn"` containing the partially-built turn

**Turn Structure (Streaming):**
```python
{
    "role": "assistant",
    "messages": [
        {"type": "reasoning", "reasoning_content": "..."},
        {"type": "content", "content": "..."},
        {"type": "tool_calls", "tool_calls": [...]},
        {"type": "tool_response", "content": "..."}  # Merged into tool_calls for display
    ]
}
```

**Behavior:**
1. Processes tokens one at a time from the stream
2. Groups tokens into "segments" based on type:
   - If token type differs from previous, creates a new segment
   - If same type, merges into the current segment
3. Handles special cases:
   - `tool_call_delta` and `tool_calls` are merged into one segment type
   - `tool` tokens create new segments when `tool_call_id` changes
   - Reasoning content is stored in `reasoning_content` field
   - Content is stored in `content` field
4. Merges tool responses with tool calls (same as `group_history`)
5. Yields a complete turn object after each token

**Streaming Segments:**
A segment is a group of tokens of the same type. Multiple segments of the same type can exist (e.g., multiple reasoning blocks if the AI reasons, calls a tool, then reasons again).

```
User -> [Reasoning1] -> [Content1] -> [ToolCalls1] -> [ToolResponse1] -> 
        [Reasoning2] -> [ToolCalls2] -> [ToolResponse2] -> [ContentFinal]
```

Each bracket is a separate segment within the turn.

## Turn Grouping Logic

### History Grouping
```
Messages: [user1, assistant1, tool1, tool_resp1, assistant2]
Turns:    [user1,    [assistant1, tool1, tool_resp1, assistant2]]
```

### Streaming Grouping
```
Tokens:   content_a, content_b, tool_call_delta_1, tool_response_1, content_c
Segments: [content: "ab"], [tool_calls: {1}], [tool_response: {1}], [content: "c"]
Turn:     {messages: [content, tool_calls+response, content]}
```

## Tool Response Merging

Tool responses are automatically merged with their corresponding tool calls for display:

```python
# Input messages:
{"role": "assistant", "tool_calls": [{"id": "tc1", "function": {"name": "search"}}]}
{"role": "tool", "tool_call_id": "tc1", "content": "Result data"}

# Merged in turn:
{"role": "assistant", "tool_calls": [{"id": "tc1", "function": {"name": "search"}, "response": "Result data"}]}
```

The `tool_response` segment type is filtered out from display, with the response attached to the tool call instead.

## Usage Examples

### Displaying Chat History
```python
turns = await channel.turncollector.group_history(await messages.get())
for turn in turns:
    if turn["role"] == "user":
        print(f"User: {turn['messages'][0]['content']}")
    else:
        print(f"Assistant: {turn['messages']}")  # Contains reasoning, content, tools
```

### Streaming Display
```python
async for partial_turn in channel.turncollector.group_stream(
    channel.send_stream("user message")
):
    if partial_turn["type"] == "turn":
        display_turn(partial_turn["content"])
    elif partial_turn["type"] == "token":
        display_token(partial_turn["content"])
```

## Best Practices

1. **Use `group_stream()` for real-time display** - Yields progressive updates
2. **Use `group_history()` for saved chats** - Groups all messages at once
3. **Filter `tool_response` for display** - Responses are merged into tool calls
4. **Respect the `index` field** - Allows targeting specific messages
5. **Don't modify turn objects** - They're built fresh each time