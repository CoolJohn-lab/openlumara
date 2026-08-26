import asyncio
import os

import core
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters


class Telegram(core.channel.Channel):
    """Talk to your AI over Telegram"""

    running = False

    dependencies = ["python-telegram-bot"]

    settings = {
        "token": "TOKEN_HERE",
        # Explicit owner authorization (PREFERRED). Set to your numeric Telegram
        # chat ID to lock the bot to a single chat. When set, every other chat
        # is ignored and trust-on-first-use is disabled.
        "authorized_chat_id": "",
        # Optional: also require the sender's Telegram @username to match this
        # (used only for the TOFU fallback below).
        "authorized_username": "",
        # Trust-on-first-use fallback. OFF by default: without an explicit
        # authorized_chat_id the bot refuses everyone. Enable only if you cannot
        # pre-configure your chat ID; the first chat to /start then claims it
        # (clearly logged).
        "allow_tofu": False,
        "use_message_streaming": True,
        "stream_tool_calls": False,
        "show_reasoning": False,
        "announce_startup": False,
        "announce_shutdown": False,
    }

    async def run(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.token:
            try:
                self.token = self.config.get("token")
            except AttributeError:
                pass

        self.app = None

        # ── Owner authorization ───────────────────────────────────────────
        # An explicit configured chat ID always wins; TOFU is an opt-in
        # fallback only.
        self.configured_chat_id = None
        self.allow_tofu = False
        self.authorized_username = ""
        try:
            cfg_id = self.config.get("authorized_chat_id")
            self.allow_tofu = bool(self.config.get("allow_tofu"))
            self.authorized_username = (self.config.get("authorized_username") or "").lstrip("@")
        except AttributeError:
            cfg_id = None
        if cfg_id is not None and str(cfg_id).strip():
            try:
                self.configured_chat_id = int(cfg_id)
            except (ValueError, TypeError):
                self.log("telegram", "Failed to parse configured authorized_chat_id.")

        # Initialize StorageText to handle the authorized chat ID
        self.auth_storage = core.storage.StorageText("telegram_chat_id")

        # Resolve the authorized chat ID: explicit config first, then the TOFU
        # store (only if TOFU is enabled). Fail-closed otherwise.
        self.authorized_chat_id = None
        if self.configured_chat_id is not None:
            self.authorized_chat_id = self.configured_chat_id
            self.log("telegram", f"Using configured authorized chat ID: {self.authorized_chat_id}")
        elif self.allow_tofu:
            stored_id = self.auth_storage.get()
            if stored_id and stored_id.strip():
                try:
                    self.authorized_chat_id = int(stored_id)
                    self.log("telegram", f"Restored TOFU chat ID: {self.authorized_chat_id}")
                except ValueError:
                    self.log("telegram", "Failed to parse stored chat ID.")
        else:
            self.log(
                "telegram",
                "No authorized_chat_id configured and TOFU disabled; bot will "
                "ignore all chats until an owner is configured.",
            )

        self._shutting_down = False

        # Queue for sequential processing of standard messages
        self.message_queue = asyncio.Queue()
        self.queue_task = None

        if not self.token:
            await self.push("Telegram channel failed: No API token provided.")
            return False

        try:
            self.app = Application.builder().token(self.token).build()
            self.app.add_handler(CommandHandler("start", self._tg_start))
            self.app.add_handler(MessageHandler(filters.TEXT, self._tg_message))

            await self.app.initialize()
            await self.app.start()
            await self.app.updater.start_polling(drop_pending_updates=True)

            self.running = True

            # Start the queue processor worker
            self.queue_task = asyncio.create_task(self._process_queue_worker())

            if self.config.get("announce_startup"):
                await self.push("Telegram channel connected.")

            while self.running and not self._shutting_down:
                await asyncio.sleep(1)

        except Exception as e:
            self.log("telegram", f"Critical Error: {e!s}")
            return False
        finally:
            # Clean up the queue task
            if self.queue_task:
                self.queue_task.cancel()
            await self._cleanup()

        return True

    async def _cleanup(self):
        if self.app:
            if self.app.updater.running:
                await self.app.updater.stop()
            if self.app.running:
                await self.app.stop()
            await self.app.shutdown()

    async def on_shutdown(self):
        if self.config.get("announce_shutdown"):
            await self.announce("Shutting down Telegram channel...", "status")
            self.running = False
            self._shutting_down = True
            return True

    def _username_allowed(self, update: Update) -> bool:
        """When an authorized_username is configured, the sender must match it."""
        if not self.authorized_username:
            return True
        user = getattr(update, "effective_user", None)
        uname = (getattr(user, "username", "") or "").lstrip("@")
        return uname.lower() == self.authorized_username.lower()

    async def _tg_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id

        # Already the owner.
        if self.authorized_chat_id is not None:
            if chat_id == self.authorized_chat_id:
                await update.message.reply_text("✅ Session started.\n")
            else:
                await update.message.reply_text("⚠️ This bot is already in use.")
            return

        # No owner yet: claim via TOFU only if it is enabled (and no explicit
        # config was provided) and the username matches any configured filter.
        if self.allow_tofu and self._username_allowed(update):
            self.authorized_chat_id = chat_id
            self.auth_storage.set(str(chat_id))
            await update.message.reply_text("✅ Session started.\n")
            self.log("telegram", f"[TOFU] Authorized chat ID: {chat_id}")
        else:
            await update.message.reply_text("⚠️ This bot is not configured for you.")
            self.log("telegram", f"Rejected /start from unauthorized chat {chat_id}")

    async def _tg_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Routes incoming messages:
        - Commands (/stop, /help) -> Process immediately (concurrently).
        - Normal text -> Add to queue (sequentially).
        """
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        # Only the authorized owner is ever served.
        if self.authorized_chat_id is not None:
            if chat_id != self.authorized_chat_id:
                return
        elif self.allow_tofu and self._username_allowed(update):
            self.authorized_chat_id = chat_id
            self.auth_storage.set(str(chat_id))
            self.log("telegram", f"[TOFU] Authorized chat ID via message: {chat_id}")
        else:
            return

        text = update.message.text.strip()
        cmd_prefix = core.config.get("core").get("cmd_prefix", "/")

        # Check if it is a command
        if text.startswith(cmd_prefix):
            # Execute commands immediately in a separate task to allow interruption
            # This allows /stop to cancel an ongoing stream processed by the queue worker
            asyncio.create_task(self._process_stream(update, context))
        else:
            # Queue normal messages for sequential processing
            await self.message_queue.put((update, context))

    async def _process_queue_worker(self):
        """
        Worker that processes messages from the queue one by one.
        This ensures normal messages don't overlap.
        """
        while self.running and not self._shutting_down:
            try:
                # Wait for a message from the queue
                update, context = await self.message_queue.get()

                chat_id = update.effective_chat.id
                user_msg = update.message.text.strip()

                # Start typing indicator before generating response
                typing_task = asyncio.create_task(self._keep_typing(chat_id))

                try:
                    if self.config.get("use_message_streaming"):
                        # Process the message (this waits for the stream to finish)
                        await self._process_stream(update, context)
                    else:
                        response = await self.send(
                            user_msg,
                            commands_authorized=(chat_id == self.authorized_chat_id),
                        )
                        if response:
                            content = response.get("content")
                            if content:
                                # send message to telegram
                                await self._send_chunked_message(context.bot, chat_id, content)
                except Exception as e:
                    self.log("telegram", f"Error in queue worker processing: {e}")
                finally:
                    # Stop typing indicator
                    if not typing_task.done():
                        typing_task.cancel()
                        try:
                            await typing_task
                        except asyncio.CancelledError:
                            pass
                    # Mark the task as done
                    self.message_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log("telegram", f"Queue worker error: {e}")
                await asyncio.sleep(1)  # Prevent tight loop on error

    async def _process_stream(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Contains the logic for streaming AI responses to the user.
        """
        chat_id = update.effective_chat.id
        user_msg = update.message.text.strip()

        # 1. Start Typing Indicator
        typing_task = asyncio.create_task(self._keep_typing(chat_id))

        # Pre-send a message like Discord does
        initial_msg = await context.bot.send_message(chat_id, "processing your request...")

        class StreamState:
            def __init__(self, initial_msg):
                self.message_obj = initial_msg
                self.full_content = ""
                self.is_running = True

        state = StreamState(initial_msg)
        edit_lock = asyncio.Lock()
        edit_interval = 1.5

        async def periodic_editor():
            while state.is_running:
                await asyncio.sleep(edit_interval)
                async with edit_lock:
                    if state.message_obj and state.full_content:
                        try:
                            await state.message_obj.edit_text(state.full_content[:4000])
                        except Exception:
                            pass

        editor_task = asyncio.create_task(periodic_editor())

        try:
            # 2. Consume the stream
            # Use a chunk size similar to Discord's MAX_CHARS
            # Commands are only authorized for the verified owner chat.
            commands_authorized = chat_id == self.authorized_chat_id
            stream = self.format_stream_for_text(
                self.send_stream(user_msg, commands_authorized=commands_authorized),
                use_markdown=False,
                chunk_size=1900,
            )

            async for token in stream:
                if token.get("type") == "new_chunk":
                    async with edit_lock:
                        # Finalize current message
                        if state.message_obj:
                            try:
                                await state.message_obj.edit_text(state.full_content[:4000])
                            except:
                                pass

                        # Start new message
                        state.message_obj = await context.bot.send_message(chat_id, "...")
                        state.full_content = ""
                    continue

                if token.get("type") != "formatted":
                    continue

                content = token.get("content", "")
                if not content:
                    continue
                if not isinstance(content, str):
                    continue

                async with edit_lock:
                    state.full_content += content

            # 3. Finalize
            async with edit_lock:
                if state.message_obj:
                    try:
                        await state.message_obj.edit_text(state.full_content[:4000])
                    except:
                        pass
                elif state.full_content:
                    try:
                        await context.bot.send_message(chat_id, state.full_content[:4000])
                    except:
                        pass

        except Exception as e:
            self.log("telegram", f"Error processing stream: {e}")
            try:
                await context.bot.send_message(chat_id, f"❌ Error: {e!s}")
            except:
                pass
        finally:
            state.is_running = False
            editor_task.cancel()
            try:
                await editor_task
            except asyncio.CancelledError:
                pass
            if not typing_task.done():
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

    async def _keep_typing(self, chat_id: int):
        try:
            while True:
                await self.app.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.log("telegram", f"Typing indicator error: {e}")

    async def _send_telegram_message(self, text: str):
        if not self.authorized_chat_id or not self.app:
            return
        await self._send_chunked_message(self.app.bot, self.authorized_chat_id, text)

    async def _send_chunked_message(self, bot, chat_id, text):
        """Sends a message to Telegram, splitting it into chunks if it's too long."""
        if not text:
            return

        max_length = 4000

        if len(text) <= max_length:
            try:
                await bot.send_message(chat_id, text, parse_mode="Markdown")
            except Exception:
                try:
                    await bot.send_message(chat_id, text)
                except Exception as e:
                    self.log("telegram", f"Failed to send message: {e}")
            return

        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            # Try to split at a newline or space within the limit
            split_idx = text.rfind("\n", 0, max_length)
            if split_idx == -1:
                split_idx = text.rfind(" ", 0, max_length)
            if split_idx == -1:
                split_idx = max_length

            chunks.append(text[:split_idx].strip())
            text = text[split_idx:].strip()

        for chunk in chunks:
            if not chunk:
                continue
            try:
                await bot.send_message(chat_id, chunk, parse_mode="Markdown")
            except Exception:
                try:
                    await bot.send_message(chat_id, chunk)
                except Exception as e:
                    self.log("telegram", f"Failed to send chunk: {e}")

    async def on_push(self, message: dict):
        content = message.get("content")

        self.log("telegram", content)

        if self.authorized_chat_id and self.app:
            # emoji_map = {
            #     "error": "🚨",
            #     "warning": "⚠️",
            #     "status": "ℹ️",
            #     "info": "💬"
            # }
            # emoji = emoji_map.get(type, "🔔")
            # safe_msg = content.replace("*", "").replace("_", "")
            # text = f"{emoji} *{type.upper()}:* {safe_msg}"
            asyncio.create_task(self._send_telegram_message(content))
