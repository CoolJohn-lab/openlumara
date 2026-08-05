# Core: The API Client (`core.APIClient`)

The `APIClient` is a wrapper around the OpenAI Python library (`openai.AsyncOpenAI`) that provides a unified interface for interacting with any OpenAI-compatible AI backend (local or cloud).

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `manager` | `Manager` | Reference to the OpenLumara manager instance. |
| `connected` | `bool` | Whether currently connected to the API. |
| `_AI` | `openai.AsyncOpenAI \| None` | The underlying OpenAI async client instance. |
| `is_streaming` | `bool` | Whether currently streaming a response. |
| `_messages` | `list` | Reserved for future use. |
| `cancel_request` | `bool` | Flag set to True to cancel an ongoing request. |
| `_httpx_client` | `httpx.AsyncClient \| None` | The underlying HTTP client (for TLS config). |
| `supports_developer_role` | `bool` | Whether the API supports the `developer` role. |

## Responsibilities

### 1. Connection Management
The `APIClient` handles connecting to the AI provider:
- **Authentication**: Validates API keys and handles authentication errors.
- **Connection Lifecycle**: Provides `connect()`, `disconnect()`, and `reconnect()` methods.
- **TLS Support**: Respects `--insecure-tls` flag for local development with self-signed certificates.
- **Auto-Reconnect**: `attempt_connect()` connects if disconnected, returns `True` if already connected.

### 2. Request Orchestration
The client abstracts LLM request details:
- **Unified Interface**: `send()` for standard responses, `send_stream()` for streaming.
- **Parameter Management**: Automatically applies config settings:
  - `model.temperature` (default 0.2)
  - `api.max_output_tokens` (default 8192)
  - `model.enable_thinking` (via `extra_body.chat_template_kwargs`)
  - `model.reasoning_effort`
  - `api.custom_fields` (arbitrary additional fields)
- **Tool Integration**: Handles tool definitions for function calling.
- **Request Cancellation**: Uses background task monitoring to cancel requests (OpenAI's async client doesn't natively support abort).
- **Debug Logging**: In debug mode, logs request structure to `debug:request`.

### 3. Response Processing
Translates raw API responses into structured data:
- **Standard Responses** (`_recv()`): Extracts content, reasoning, and tool calls. Returns dict with `content`, `reasoning_content`, `tool_calls`, and `role`.
- **Streaming Responses** (`_recv_stream()`): Async generator yielding typed tokens:
  - `content` → Normal text tokens
  - `reasoning` → Thinking/reasoning tokens
  - `tool_call_delta` → Streaming tool call argument updates
  - `tool_calls` → Full assembled tool call object
  - `tool` → Tool response tokens
  - `token_usage` → Token usage data
  - `prompt_progress` → Prompt progress (if supported)
  - `timings` → Native timing data
  - `error` → Error tokens

## Key Methods

| Method | Description |
| :--- | :--- |
| `connect(silent=False)` | Establishes connection to API. Returns `True` on success, `APIError` on failure. |
| `disconnect()` | Closes HTTP client and resets state. Returns `True`. |
| `reconnect()` | Disconnects and reconnects. |
| `attempt_connect()` | Connects if disconnected, returns `True` if already connected. |
| `send(context, use_tools=True, tools=None, use_thinking=True, **kwargs)` | Sends context to AI, returns response dict or `APIError`. |
| `send_stream(context, use_tools=True, tools=None, use_thinking=True, **kwargs)` | Sends context, returns async generator yielding tokens. |
| `cancel()` | Sets `cancel_request = True` to abort ongoing request. Returns `True` when cancelled. |
| `list_models()` | Returns alphabetically sorted list of available model IDs. |
| `get_model()` | Returns current model name. |
| `set_model(name)` | Sets the current model name. |
| `get_status()` | Returns dict with `connected`, `url`, and `model`. |

## Request Structure

The `_request()` method builds:
```python
{
    "model": config.model.name,
    "messages": context,
    "tools": tools,
    "stream": stream,
    "temperature": 0.2,
    "max_completion_tokens": 8192,
    "extra_body": {
        "chat_template_kwargs": {"enable_thinking": True/False},
        "return_progress": True
    },
    # reasoning_effort (if not "none")
    # stream_options.include_usage (if streaming)
    # custom_fields (from config)
    # **kwargs
}
```

## Error Handling

Errors are wrapped in `APIError` class with user-friendly messages:
- `BadRequestError` → "Bad request" or "Model not found"
- `AuthenticationError` → "Authentication failed"
- `APIConnectionError` → "Failed to connect to the API"
- `NotFoundError` → "Model with that name does not exist!"
- `RateLimitError` → "Rate limit exceeded"
- `APIStatusError` → "API Status Error"
- Generic `Exception` → Details in debug mode

## `APIError` Class

Simple error holder for passing errors to channels:
```python
class APIError:
    def __init__(self, message=None, exc=None):
        self.message = message
        self.exc = exc  # Original exception if relevant
    
    def __str__(self):
        # Combines message and exception details
```
