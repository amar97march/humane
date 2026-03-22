"""Telegram Bot — async handlers for the Humane companion."""

from __future__ import annotations
import asyncio
import logging
import re
import time
from typing import Optional

from humane.conductor import Conductor
from humane.core.config import HumaneConfig, load_config
from humane.bot.brain import Brain
from humane.bot.conversation import ConversationEngine
from humane.bot.scheduler import Scheduler
from humane.bot.voice import VoiceProcessor

logger = logging.getLogger("humane.telegram")


class HumaneBot:
    """The main Telegram bot class."""

    def __init__(self, config: Optional[HumaneConfig] = None):
        self.config = config or HumaneConfig()
        self.conductor = Conductor(config=self.config, db_path=self.config.db_path)
        self.conversation = ConversationEngine(
            llm_provider=self.config.llm_provider,
            llm_model=self.config.llm_model,
            api_key=self.config.llm_api_key,
            base_url=self.config.llm_base_url,
        )
        self.brain = Brain(self.conductor, self.conversation)
        self.scheduler = Scheduler(self.brain)
        self.voice = VoiceProcessor(self.config)
        self._app = None

    async def start(self):
        """Start the Telegram bot + scheduler."""
        from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters

        if not self.config.telegram_bot_token:
            logger.error("No Telegram bot token configured. Run 'humane init' first.")
            return

        self._app = ApplicationBuilder().token(self.config.telegram_bot_token).build()

        # Register handlers
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("state", self._handle_state))
        self._app.add_handler(CommandHandler("goals", self._handle_goals))
        self._app.add_handler(CommandHandler("remind", self._handle_remind))
        self._app.add_handler(CommandHandler("help", self._handle_help))
        self._app.add_handler(CallbackQueryHandler(self._handle_callback))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        if self.config.voice_enabled:
            self._app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self._handle_voice))

        # Set up scheduler to send messages via bot
        async def send_message(chat_id: int, text: str):
            await self._app.bot.send_message(chat_id=chat_id, text=text)

        self.scheduler.set_message_sender(send_message)

        # Start scheduler in background
        asyncio.create_task(self.scheduler.start())

        logger.info("Humane bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

        logger.info("Humane bot is running. Press Ctrl+C to stop.")

        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.stop()

    async def stop(self):
        """Stop the bot and scheduler."""
        await self.scheduler.stop()
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        logger.info("Humane bot stopped.")

    async def _handle_start(self, update, context):
        """Handle /start command — onboarding."""
        user = update.effective_user
        chat_id = update.effective_chat.id

        self.brain._ensure_entity(chat_id, user.first_name or user.username or "")

        welcome = (
            f"Hey {user.first_name or 'there'}! I'm your Humane companion.\n\n"
            "I'm not a regular bot — I'll remember things, follow up on tasks, "
            "and sometimes bring stuff up on my own. Think of me as a thoughtful colleague "
            "who actually pays attention.\n\n"
            "Just talk to me naturally. If you want me to remember something, just tell me. "
            "I'll figure out the rest.\n\n"
            "A few commands if you need them:\n"
            "/remind <task> — I'll follow up on this\n"
            "/state — how I'm feeling right now\n"
            "/goals — what we're working on\n"
            "/help — more options"
        )
        await update.message.reply_text(welcome)

    async def _handle_message(self, update, context):
        """Handle regular text messages — the main conversation loop."""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username or ""
        text = update.message.text

        response = await self.brain.on_user_message(chat_id, user_id, user_name, text)

        if response:
            await update.message.reply_text(response)

    async def _handle_voice(self, update, context):
        """Handle voice/audio messages — transcribe and route through brain."""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username or ""

        try:
            # Get the voice or audio file
            if update.message.voice:
                file = await update.message.voice.get_file()
                audio_format = "ogg"
            elif update.message.audio:
                file = await update.message.audio.get_file()
                # Detect format from mime_type or file name
                mime = update.message.audio.mime_type or ""
                if "mp3" in mime or "mpeg" in mime:
                    audio_format = "mp3"
                elif "wav" in mime:
                    audio_format = "wav"
                elif "m4a" in mime or "mp4" in mime:
                    audio_format = "m4a"
                elif "webm" in mime:
                    audio_format = "webm"
                else:
                    audio_format = "ogg"
            else:
                await update.message.reply_text("I couldn't understand that audio.")
                return

            # Download the file bytes
            audio_bytes = await file.download_as_bytearray()

            # Transcribe
            transcribed_text = await self.voice.transcribe(bytes(audio_bytes), format=audio_format)

            if not transcribed_text:
                await update.message.reply_text("I couldn't understand that audio.")
                return

            # Route through brain as if user typed the text
            response = await self.brain.on_user_message(chat_id, user_id, user_name, transcribed_text)

            prefix = f"I heard: '{transcribed_text}'\n\n"
            if response:
                await update.message.reply_text(prefix + response)
            else:
                await update.message.reply_text(prefix.strip())

        except Exception as e:
            logger.error("Voice processing error: %s", e, exc_info=True)
            await update.message.reply_text("I couldn't understand that audio.")

    async def _handle_state(self, update, context):
        """Handle /state — show current HumanState."""
        state = self.conductor.get_state_snapshot()

        def bar(val, width=10):
            filled = int(abs(val) * width)
            return "\u2588" * filled + "\u2591" * (width - filled)

        msg = "HUMANSTATE\n\n"
        msg += f"energy  {bar(state['energy'])}  {state['energy']:.2f}\n"
        msg += f"mood    {bar(abs(state['mood']))}  {state['mood']:+.2f}\n"
        msg += f"fatigue {bar(state['fatigue'])}  {state['fatigue']:.2f}\n"
        msg += f"boredom {bar(state['boredom'])}  {state['boredom']:.2f}\n"
        msg += f"social  {bar(state['social_load'])}  {state['social_load']:.2f}\n"
        msg += f"focus   {bar(state['focus'])}  {state['focus']:.2f}\n"
        msg += f"\nDQ multiplier: {self.conductor.human_state.decision_quality_multiplier:.2f}"
        msg += f"\nPreferred task: {self.conductor.human_state.preferred_task_type.value}"

        queue = self.conductor.get_hold_queue()
        if queue:
            msg += f"\n\n{len(queue)} actions in hold queue"

        await update.message.reply_text(msg)

    async def _handle_goals(self, update, context):
        """Handle /goals — show active goals."""
        goals = self.conductor.goal_engine.active_goals()

        if not goals:
            await update.message.reply_text("No active goals right now. Tell me what you're working on and I'll track it.")
            return

        msg = "ACTIVE GOALS\n\n"
        for i, goal in enumerate(goals, 1):
            roi = self.conductor.goal_engine.compute_roi(goal)
            progress = f"{goal.milestones_completed}/{goal.milestones_total}" if goal.milestones_total else "tracking"
            msg += f"{i}. {goal.description}\n   Progress: {progress} | ROI: {roi:.2f}\n\n"

        await update.message.reply_text(msg)

    async def _handle_remind(self, update, context):
        """Handle /remind <task> — register a reminder."""
        text = update.message.text.replace("/remind", "").strip()

        if not text:
            await update.message.reply_text("What should I remind you about? Usage: /remind call Arjun about the proposal")
            return

        chat_id = update.effective_chat.id

        # Parse time hints
        remind_at = None
        time_match = re.search(r'(?:in\s+)?(\d+)\s*(hours?|hrs?|minutes?|mins?|days?)', text, re.IGNORECASE)
        if time_match:
            amount = int(time_match.group(1))
            unit = time_match.group(2).lower()
            if 'hour' in unit or 'hr' in unit:
                remind_at = time.time() + amount * 3600
            elif 'min' in unit:
                remind_at = time.time() + amount * 60
            elif 'day' in unit:
                remind_at = time.time() + amount * 86400
            text = text[:time_match.start()].strip() or text

        if "tomorrow" in text.lower():
            remind_at = time.time() + 86400
            text = text.lower().replace("tomorrow", "").strip()

        self.brain.register_reminder(chat_id, text, remind_at)

        if remind_at:
            hours = (remind_at - time.time()) / 3600
            if hours < 1:
                time_str = f"{int(hours * 60)} minutes"
            elif hours < 24:
                time_str = f"{hours:.0f} hours"
            else:
                time_str = f"{hours / 24:.0f} days"
            await update.message.reply_text(f"Got it — I'll remind you about \"{text}\" in {time_str}. And I won't let you forget.")
        else:
            await update.message.reply_text(f"Noted — \"{text}\". I'll start checking in on this tomorrow.")

    async def _handle_help(self, update, context):
        msg = (
            "Just talk to me like a person. I'll remember things, follow up, and sometimes bring stuff up on my own.\n\n"
            "Commands:\n"
            "/remind <task> — I'll follow up on this\n"
            "/remind <task> in 2 hours — timed reminder\n"
            "/remind <task> tomorrow — next day\n"
            "/state — my current internal state\n"
            "/goals — what we're tracking\n"
            "/help — this message\n\n"
            "But honestly, you can just say things like:\n"
            "\"remind me to call Arjun\"\n"
            "\"add a goal: close the DesignStudio deal\"\n"
            "\"how's my relationship with Priya?\"\n"
            "I'll figure it out."
        )
        await update.message.reply_text(msg)

    async def _handle_callback(self, update, context):
        """Handle inline keyboard button presses."""
        query = update.callback_query
        await query.answer()

        data = query.data
        if data.startswith("approve_"):
            hold_id = data.replace("approve_", "")
            self.conductor.approve_hold(hold_id)
            await query.edit_message_text("Approved.")
        elif data.startswith("reject_"):
            hold_id = data.replace("reject_", "")
            self.conductor.reject_hold(hold_id)
            await query.edit_message_text("Rejected.")


async def run_bot(config: Optional[HumaneConfig] = None):
    """Entry point to run the bot."""
    bot = HumaneBot(config)
    await bot.start()
