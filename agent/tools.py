import os
import yaml
import logging
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def obtener_horario() -> dict:
    info = cargar_info_negocio()
    return {"horario": info.get("negocio", {}).get("horario", "No disponible")}


def buscar_en_knowledge(consulta: str) -> str:
    resultados = []
    knowledge_dir = "knowledge"
    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."
    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue
    return "\n---\n".join(resultados) if resultados else "No encontré información específica sobre eso."


async def registrar_lead_n8n(telefono: str, nombre: str, interes: str = "") -> str:
    webhook_url = os.getenv("N8N_WEBHOOK_URL")
    if not webhook_url:
        logger.warning("N8N_WEBHOOK_URL no configurado — lead guardado solo en logs")
        logger.info(f"Lead local — nombre:{nombre} tel:{telefono} interes:{interes}")
        return "Lead registrado localmente."

    payload = {
        "nombre": nombre,
        "telefono": telefono,
        "interes": interes,
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(webhook_url, json=payload)
            if r.status_code in (200, 201):
                logger.info(f"Lead enviado a n8n — nombre:{nombre} tel:{telefono}")
                return "Lead registrado en CRM correctamente."
            else:
                logger.error(f"Error n8n webhook: {r.status_code} — {r.text}")
                return "Lead registrado localmente (fallo webhook)."
    except Exception as e:
        logger.error(f"Excepcion llamando n8n: {e}")
        return "Lead registrado localmente (excepcion)."
