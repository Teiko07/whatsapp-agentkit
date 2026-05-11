# agent/audio.py — Transcripción de audios con OpenAI Whisper
# Generado por AgentKit

"""
Convierte notas de voz de WhatsApp en texto para que Claude pueda procesarlas.
Usa la API de OpenAI Whisper — barata (~0,006 $/min) y muy precisa en español.
"""

import io
import os
import logging
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(override=True)
logger = logging.getLogger("agentkit")

# Cliente de OpenAI (solo se usa para transcripción de audio)
cliente_openai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


async def transcribir_audio(audio_bytes: bytes, nombre_archivo: str = "audio.ogg") -> str:
    """
    Transcribe un audio (en bytes) a texto usando Whisper API.

    Args:
        audio_bytes: contenido binario del audio
        nombre_archivo: nombre con extension correcta (.ogg, .mp3, .wav, .m4a)

    Returns:
        Texto transcrito en español. Cadena vacía si falla.
    """
    if not audio_bytes:
        return ""
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY no configurada — no se puede transcribir audio")
        return ""

    try:
        archivo = io.BytesIO(audio_bytes)
        archivo.name = nombre_archivo
        resp = await cliente_openai.audio.transcriptions.create(
            model="whisper-1",
            file=archivo,
            language="es",
        )
        texto = (resp.text or "").strip()
        logger.info(f"Audio transcrito ({len(audio_bytes)} bytes): {texto[:120]}")
        return texto
    except Exception as e:
        logger.error(f"Error transcribiendo audio: {e}")
        return ""
