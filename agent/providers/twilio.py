# agent/providers/twilio.py — Adaptador para Twilio WhatsApp
# Generado por AgentKit

import os
import logging
import base64
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


def _extension_por_content_type(content_type: str) -> str:
    """Devuelve la extensión correcta según el MIME del audio (Whisper la necesita)."""
    ct = (content_type or "").lower()
    if "ogg" in ct or "opus" in ct:
        return "ogg"
    if "mpeg" in ct or "mp3" in ct:
        return "mp3"
    if "wav" in ct:
        return "wav"
    if "mp4" in ct or "m4a" in ct or "aac" in ct:
        return "m4a"
    if "webm" in ct:
        return "webm"
    return "ogg"  # WhatsApp/Twilio mandan ogg/opus por defecto


class ProveedorTwilio(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Twilio."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    async def _descargar_media(self, url: str) -> bytes | None:
        """Descarga un archivo multimedia de Twilio con autenticación básica."""
        if not all([self.account_sid, self.auth_token]):
            logger.warning("No se puede descargar media: credenciales Twilio faltantes")
            return None
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        try:
            # follow_redirects=True: Twilio devuelve un 302 a un bucket S3 firmado
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                r = await client.get(url, headers=headers)
                if r.status_code == 200:
                    return r.content
                logger.error(f"Error descargando media Twilio: {r.status_code}")
                return None
        except Exception as e:
            logger.error(f"Excepción descargando media: {e}")
            return None

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload form-encoded de Twilio. Soporta texto y audio."""
        form = await request.form()
        texto = form.get("Body", "") or ""
        telefono = (form.get("From", "") or "").replace("whatsapp:", "")
        mensaje_id = form.get("MessageSid", "") or ""

        # ¿Hay media adjunta?
        try:
            num_media = int(form.get("NumMedia", "0") or "0")
        except ValueError:
            num_media = 0

        audio_bytes: bytes | None = None
        nombre_audio = "audio.ogg"

        if num_media > 0:
            media_url = form.get("MediaUrl0", "") or ""
            content_type = (form.get("MediaContentType0", "") or "").lower()
            if media_url and content_type.startswith("audio/"):
                audio_bytes = await self._descargar_media(media_url)
                nombre_audio = f"audio.{_extension_por_content_type(content_type)}"
                if audio_bytes:
                    logger.info(f"Audio recibido de {telefono} ({len(audio_bytes)} bytes, {content_type})")

        # Si no hay texto ni audio descargado, descartamos
        if not texto and not audio_bytes:
            return []

        return [MensajeEntrante(
            telefono=telefono,
            texto=texto,
            mensaje_id=mensaje_id,
            es_propio=False,
            audio_bytes=audio_bytes,
            nombre_audio=nombre_audio,
        )]

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Twilio API."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Variables de Twilio no configuradas")
            return False
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "Body": mensaje,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, data=data, headers=headers)
            if r.status_code != 201:
                logger.error(f"Error Twilio: {r.status_code} — {r.text}")
            return r.status_code == 201
