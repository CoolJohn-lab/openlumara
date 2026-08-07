import core
import readline
import asyncio
import concurrent.futures

import rich
import rich.console
import rich.text
import rich.status
import rich.progress
import rich.markdown
import rich.traceback

def plaintext(text):
    """helper that makes the Rich library not auto-color text"""

    return rich.text.Text(text)

class Cli(core.channel.Channel):
    settings = {
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False
        }
    }

    dependencies = ["rich"]

    async def on_ready(self):
        self.console = rich.console.Console()
        self.console.print(plaintext("-"*40))

        self.console.print(plaintext(f"Welcome to OpenLumara V{core.version}"))
        self.console.print("Type /new to start a new session, /help for help, /chats to see your chats")
        self.console.print("Type /quit or /exit to quit")
        self.console.print(plaintext("-"*40))

        # install rich's traceback handler
        rich.traceback.install(show_locals=True)

    async def _get_input(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, "user> ")

    async def run(self):
        while True:
            try:
                user_input = await self._get_input()
            except (KeyboardInterrupt, EOFError):
                self.console.print()
                await self.manager.shutdown()
                break

            _, cmd, _ = await self.commands._extract_cmd(user_input)
            if cmd in ("quit", "exit"):
                await self.manager.shutdown()
                break

            processing_prompt = False
            first_processing_prompt = True
            progress = rich.progress.Progress(expand=False, transient=False)
            progress_task = None

            sending_prompt = True
            sending = rich.status.Status("Sending", console=self.console)
            sending.start()
            try:
                async for token in self.format_stream_for_text(
                    self.send_stream(user_input, commands_authorized=True),
                    use_markdown=False
                ):
                    token_type = token.get("type")
                    token_content = token.get("content")

                    if token_type in ("user_message", "token_usage"):
                        continue

                    if sending_prompt:
                        sending.stop()
                        sending_prompt = False

                    if token_type == "prompt_progress":
                        if not processing_prompt:
                            if first_processing_prompt:
                                first_processing_prompt = False
                            else:
                                # create a newline so that the progress bar doesnt replace the content
                                self.console.print()

                            # display a progress bar
                            progress.start()
                            progress_task = progress.add_task("[lime]Processing..", total=1)
                            processing_prompt = True

                        progress.update(progress_task, completed=(token_content.get("processed") / token_content.get("total")), refresh=True)

                    if token_type != "formatted":
                        continue

                    if processing_prompt:
                        # remove the progress bar upon receival of the first non-progress token
                        progress.remove_task(progress_task)
                        progress.stop()
                        processing_prompt = False

                    self.console.print(token_content, end="")
            except asyncio.CancelledError:
                self.console.print("\n[cyan]cancelled.[/]")
            except KeyboardInterrupt:
                self.console.print("\n[cyan]cancelled.[/]")
            finally:
                progress.stop()

            self.console.print()

    def on_log(self, category: str, message: str):
        if category == "toolcall":
            # SKIP
            return

        if not hasattr(self, 'console'):
            return

        cat_str = rf"\[{category.upper()}] " if category else ""

        self.console.print(f"[bold]{cat_str}[/bold]{message}")
