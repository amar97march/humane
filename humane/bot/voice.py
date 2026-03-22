"""Voice processing — transcribe audio via OpenAI Whisper API or local whisper."""

from __future__ import annotations

import io
import logging
from typing import Optional

import httpx

logger = logging.getLogger("humane.voice")

SUPPORTED_FORMATS = {"ogg", "mp3", "wav", "m4a", "webm"}

# Map format to MIME type for multipart upload
_MIME_TYPES = {
    "ogg": "audio/ogg",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/m4a",
    "webm": "audio/webm",
}


class VoiceProcessor:
    """Transcribes audio to text using OpenAI Whisper API or local whisper."""

    def __init__(self, config):
        self.api_key: str = config.llm_api_key
        self.provider: str = getattr(config, "voice_provider", "openai")
        self.model: str = getattr(config, "whisper_model", "whisper-1")
        self.enabled: bool = getattr(config, "voice_enabled", True)
        self._local_whisper = None

    async def transcribe(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data.
            format: Audio format — one of ogg, mp3, wav, m4a, webm.

        Returns:
            Transcribed text string.

        Raises:
            ValueError: If format is unsupported.
            RuntimeError: If transcription fails.
        """
        if format not in SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported audio format: {format}. Supported: {SUPPORTED_FORMATS}")

        if self.provider == "openai" and self.api_key:
            return await self._transcribe_openai(audio_bytes, format)
        else:
            return await self._transcribe_local(audio_bytes, format)

    async def _transcribe_openai(self, audio_bytes: bytes, format: str) -> str:
        """Transcribe using OpenAI Whisper API."""
        url = "https://api.openai.com/v1/audio/transcriptions"
        filename = f"audio.{format}"
        mime_type = _MIME_TYPES.get(format, "application/octet-stream")

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (filename, audio_bytes, mime_type)},
                data={"model": self.model},
            )

        if response.status_code != 200:
            logger.error("OpenAI Whisper API error %d: %s", response.status_code, response.text)
            raise RuntimeError(f"Whisper API returned {response.status_code}: {response.text}")

        result = response.json()
        text = result.get("text", "").strip()
        logger.info("Transcribed %d bytes of %s audio -> %d chars", len(audio_bytes), format, len(text))
        return text

    async def _transcribe_local(self, audio_bytes: bytes, format: str) -> str:
        """Transcribe using local whisper library as fallback."""
        import asyncio

        try:
            import whisper
        except ImportError:
            raise RuntimeError(
                "Local whisper not available. Install with: pip install openai-whisper  "
                "Or set voice_provider='openai' with a valid llm_api_key."
            )

        if self._local_whisper is None:
            logger.info("Loading local whisper model (base)...")
            self._local_whisper = whisper.load_model("base")

        # whisper expects a file path or numpy array — write to temp file
        import tempfile
        import os

        suffix = f".{format}"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._local_whisper.transcribe(tmp_path),
            )
            text = result.get("text", "").strip()
            logger.info("Local whisper transcribed %d bytes -> %d chars", len(audio_bytes), len(text))
            return text
        finally:
            os.unlink(tmp_path)
