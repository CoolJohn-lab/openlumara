import asyncio
import hmac
import json
import socket
import time
import uuid

import core
import fastapi
import fastapi.middleware.cors
import fastapi.responses
import uvicorn

# -------------------------
#   CONFIGURATION
# -------------------------


class ApiBridge(core.channel.Channel):
    """
    Lets you use any application or UI (for example, koboldlite, openwebui, etc) to talk to your OpenLumara instance. Simply connect your chosen application to the port you specify in this channel's settings.
    """

    settings = {
        "network_mode": {
            "type": "select",
            "options": {
                "local": "Allows only the device OpenLumara is running on to access the API bridge (sets hostname to `localhost`)",
                "internet": "Allows any device to access the API bridge (sets hostname to `0.0.0.0`)",
                "custom": "Use the custom hostname defined below",
            },
            "default": "local",
        },
        "custom_host": {
            "description": "If you want to use a custom hostname, set it here. If you don't know what that is, don't bother with this! Just use the network mode setting on either local or internet.",
            "default": None,
        },
        "port": {"type": "number", "description": "The port for the API server.", "default": 8000},
        "api_key_required": {
            "type": "boolean",
            "description": "Whether to require an API key to use this api endpoint. Strongly recommended - when on, requests without a valid key are rejected. Only turn this off for a fully trusted, non-exposed local setup.",
            "default": True,
        },
        "api_key": {
            "type": "string",
            "description": "Your chosen API key. This acts like a password, so choose a good one! There is deliberately no usable default - if this is left empty while api_key_required is on, ALL requests are rejected until you set one.",
            "default": None,
        },
        "cors_allow_origins": {
            "type": "string",
            "description": "Comma-separated list of web origins allowed to make cross-origin (browser) requests. Leave empty (the default) to allow none. Set to `*` only if you understand the risk of any website being able to call your API.",
            "default": "",
        },
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False,
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False,
        },
    }

    dependencies = ["fastapi", "uvicorn"]
    # pydantic and httpx are already included with openlumara

    # -------------------------
    #   EVENT HANDLERS
    # -------------------------

    async def on_ready(self):
        network_mode = self.config.get("network_mode")
        self.host = None
        self.port = self.config.get("port")
        match network_mode:
            case "local":
                self.host = "127.0.0.1"
            case "internet":
                self.host = "0.0.0.0"
            case "custom":
                self.host = self.config.get("custom_host")
            case _:
                self.host = "127.0.0.1"

        self.server = None
        self.server_running = False

    async def run(self):
        """The main loop: Starts the FastAPI server."""
        app = fastapi.FastAPI(title="OpenLumara OpenAI Bridge")

        # CORS: only allow the origins explicitly configured (default: none).
        # This does not affect non-browser clients (koboldlite, openwebui, curl,
        # etc.), which are not subject to CORS - it only stops arbitrary websites
        # from calling the API from a user's browser.
        cors_raw = self.config.get("cors_allow_origins", "") or ""
        allowed_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
        app.add_middleware(
            fastapi.middleware.cors.CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # require API key if set up that way
        @app.middleware("http")
        async def auth_middleware(request: fastapi.Request, call_next):
            # attach the authentication result so route handlers can decide
            # whether privileged actions (commands) are allowed
            request.state.authenticated = self._check_api_key(request)
            if self.config.get("api_key_required", True) and not request.state.authenticated:
                return fastapi.responses.JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "message": "Invalid API key",
                            "type": "invalid_request_error",
                            "param": None,
                            "code": "invalid_api_key",
                        }
                    },
                )
            return await call_next(request)

        @app.get("/v1")
        async def index():
            return fastapi.responses.RedirectResponse("/v1/health", status_code=307)

        @app.post("/v1")
        async def completions_redirect():
            return fastapi.responses.RedirectResponse("/v1/chat/completions", status_code=307)

        @app.get("/v1/health")
        async def health():
            return {"status": "OK"}

        @app.get("/v1/models")
        async def list_models():
            """Returns a fake model list that basically just contains openlumara as a model. Use the `/model` command to switch models inside openlumara."""
            return {
                "object": "list",
                "data": [
                    {
                        "id": "openlumara",
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "openlumara",
                    }
                ],
            }

        @app.post("/v1/chat/completions")
        async def chat_completions(request: fastapi.Request):
            body = await request.json()

            if not body.get("messages"):
                raise fastapi.HTTPException(status_code=400, detail="No messages provided")

            last_msg = body["messages"][-1]
            stream = body.get("stream", False)

            # only authenticated requests may run privileged /commands
            authorized = bool(getattr(request.state, "authenticated", False))

            if stream:
                return fastapi.responses.StreamingResponse(
                    self._stream_handler(last_msg.get("content", ""), "openlumara", authorized),
                    media_type="text/event-stream",
                )
            return await self._completion_handler(
                last_msg.get("content", ""), body.get("model", "openlumara"), authorized
            )

        # warn about insecure / lockout configurations at startup
        if not self.config.get("api_key_required", True):
            self.log(
                "api bridge",
                "WARNING: api_key_required is off - anyone who can reach this port can use your AI. "
                "Enable it (and set an api_key) unless this is a trusted, non-exposed local setup.",
            )
        elif not self.config.get("api_key"):
            self.log(
                "api bridge",
                "WARNING: api_key_required is on but no api_key is set - ALL requests will be rejected. "
                "Set an api_key in this channel's settings.",
            )

        # Start the server with SO_REUSEADDR to handle "address already in use" errors
        # Create a socket with SO_REUSEADDR
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(5)

            config = uvicorn.Config(app, host=self.host, port=self.port, log_level="error")
            self.server = uvicorn.Server(config)

            self.log("api bridge", f"The API bridge is up and running on {self.host}:{self.port}")
            self.server_running = True
            await self.server.serve(sockets=[sock])
            self.server_running = False
            sock.close()
        except Exception as e:
            self.log("api bridge", f"Error while starting API bridge: {core.detail_error(e)}")

    async def on_shutdown(self):
        # this is a flag exposed by uvicorn itself, which causes it to start gracefully shutting down when set
        self.server.should_exit = True

        # wait for uvicorn to actually finish shutting down
        try:
            await asyncio.wait_for(self.server.shutdown(), timeout=5.0)
        except (TimeoutError, AttributeError):
            # fallback: just give it a moment to release the socket
            await asyncio.sleep(0.5)

        self.log("api bridge", "API bridge server shut down successfully.")

    def _check_api_key(self, request):
        """Constant-time verification of the bearer token in the Authorization
        header. Returns True only when a non-empty API key is configured AND the
        header exactly matches it. If no key is set, there is nothing to match
        against, so the request is treated as unauthenticated."""
        api_key = self.config.get("api_key")
        if not api_key:
            # no usable key configured -> cannot authenticate anyone
            return False
        auth_header = request.headers.get("Authorization") or ""
        expected = f"Bearer {api_key}"
        return hmac.compare_digest(auth_header, expected)

    async def _completion_handler(self, message, model, commands_authorized=False):
        try:
            # send the request to the framework and format it
            response_dict = await self.send(message, commands_authorized=commands_authorized)
            response_dict = self.format_message(response_dict)
            content = response_dict.get("content", "")

            # return the response as a full openAI-compatible json object
            return fastapi.responses.JSONResponse(
                {
                    "id": f"chatcmpl-{uuid.uuid4()}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }
            )
        except Exception as e:
            self.log(self.name, f"Error in completion: {e!s}")
            return fastapi.responses.JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "message": str(e),
                        "type": "server_error",
                        "param": None,
                        "code": "internal_error",
                    }
                },
            )

    async def _stream_handler(self, message, model, commands_authorized=False):
        try:
            chat_id = f"chatcmpl-{uuid.uuid4()}"
            created_time = int(time.time())

            # Initial empty chunk to satisfy some clients
            yield f"data: {self._openai_chunk(chat_id, created_time, model, '')}\n\n"

            try:
                async for token in self.format_stream_for_text(
                    self.send_stream(message, commands_authorized=commands_authorized)
                ):
                    token_type = token.get("type")
                    token_content = token.get("content")

                    if token_type == "formatted":
                        yield f"data: {self._openai_chunk(chat_id, created_time, model, token_content)}\n\n"
            finally:
                yield "data: [DONE]\n\n"

        except Exception as e:
            self.log(self.name, f"Error in stream: {core.detail_error(e)}")
            yield f'data: {{"error": "{e!s}"}}\n\n'

    def _openai_chunk(self, chat_id, created, model, delta):
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}],
        }
        return json.dumps(chunk)

    async def on_push(self, msg):
        # no
        pass

    def on_log(self, cat, msg):
        # no
        return
