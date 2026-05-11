# agent/tools.py — Herramientas del agente
# Generado por AgentKit

"""
Herramientas específicas de Clínica Dental Sonrisa.
Extienden las capacidades del agente más allá de responder texto:
- Triaje por urgencia
- Agendar citas
- Registrar leads y pedidos
- Soporte post-venta / seguimiento
- Buscar en /knowledge
"""

import os
import re
import yaml
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from agent.memory import async_session, Cita, Lead

logger = logging.getLogger("agentkit")


# ════════════════════════════════════════════════════════════
# Carga de información del negocio
# ════════════════════════════════════════════════════════════

def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario y si la clínica está abierta ahora."""
    info = cargar_info_negocio()
    horario = info.get("negocio", {}).get("horario", "No disponible")
    ahora = datetime.now()
    dia = ahora.weekday()  # 0=L, 6=D
    hora = ahora.hour + ahora.minute / 60
    abierto = False
    if dia <= 4:  # L-V
        abierto = (9 <= hora < 14) or (16 <= hora < 20)
    elif dia == 5:  # Sábado
        abierto = 10 <= hora < 14
    return {"horario": horario, "esta_abierto": abierto}


# ════════════════════════════════════════════════════════════
# Triaje por urgencia
# ════════════════════════════════════════════════════════════

PALABRAS_URGENCIA_ALTA = [
    "dolor agudo", "muchísimo dolor", "no puedo dormir", "no aguanto", "no soporto",
    "hinchado", "hinchazón", "inflamado", "inflamación facial", "cara hinchada",
    "absceso", "pus", "infección", "fiebre",
    "sangrado", "sangra mucho", "no para de sangrar",
    "golpe", "traumatismo", "se me cayó el diente", "diente roto", "fractura",
    "accidente", "se me partió",
]

PALABRAS_URGENCIA_MEDIA = [
    "dolor", "duele", "molestia", "sensibilidad", "frío", "calor",
    "empaste caído", "se me cayó el empaste", "corona caída", "diente que se mueve",
    "pieza floja", "encía sangra",
]


def clasificar_urgencia(texto: str) -> str:
    """
    Clasifica un mensaje según urgencia dental.
    Retorna: "alta" | "media" | "baja".
    """
    t = texto.lower()
    if any(p in t for p in PALABRAS_URGENCIA_ALTA):
        return "alta"
    if any(p in t for p in PALABRAS_URGENCIA_MEDIA):
        return "media"
    return "baja"


def mensaje_segun_urgencia(urgencia: str) -> str:
    """Devuelve el mensaje recomendado según el nivel de urgencia."""
    if urgencia == "alta":
        return (
            "Suena urgente, lo siento mucho 😟 Te conseguimos cita HOY mismo. "
            "Si estamos fuera de horario, llama YA al 93 692 00 00 (recargo de 30 € fuera de horario). "
            "¿Me dices tu nombre y desde qué hora puedes venir hoy?"
        )
    if urgencia == "media":
        return (
            "Vamos a echarle un vistazo cuanto antes 🦷 Te puedo agendar en las próximas 24-48h. "
            "¿Te viene mejor mañana por la mañana o por la tarde?"
        )
    return (
        "¡Genial! Te agendo en la próxima semana disponible 📅 "
        "Recuerda que la primera visita es gratis e incluye radiografía panorámica. "
        "¿Qué día de la próxima semana te viene mejor?"
    )


# ════════════════════════════════════════════════════════════
# Agendar citas
# ════════════════════════════════════════════════════════════

async def reservar_cita(
    telefono: str,
    nombre: str,
    fecha: str,
    servicio: str,
    urgencia: str = "baja",
) -> dict:
    """Crea una nueva cita en la base de datos."""
    async with async_session() as session:
        cita = Cita(
            telefono=telefono,
            nombre=nombre,
            fecha=fecha,
            servicio=servicio,
            urgencia=urgencia,
            estado="pendiente",
        )
        session.add(cita)
        await session.commit()
        await session.refresh(cita)
        logger.info(f"Cita reservada #{cita.id} — {nombre} ({telefono}) — {fecha}")
        return {
            "id": cita.id,
            "nombre": nombre,
            "fecha": fecha,
            "servicio": servicio,
            "urgencia": urgencia,
        }


async def listar_citas(telefono: str) -> list[dict]:
    """Devuelve las citas activas de un paciente."""
    async with async_session() as session:
        query = (
            select(Cita)
            .where(Cita.telefono == telefono, Cita.estado != "cancelada")
            .order_by(Cita.creada.desc())
        )
        result = await session.execute(query)
        citas = result.scalars().all()
        return [
            {
                "id": c.id,
                "fecha": c.fecha,
                "servicio": c.servicio,
                "urgencia": c.urgencia,
                "estado": c.estado,
            }
            for c in citas
        ]


async def cancelar_cita(cita_id: int) -> bool:
    """Cancela una cita por ID."""
    async with async_session() as session:
        cita = await session.get(Cita, cita_id)
        if not cita:
            return False
        cita.estado = "cancelada"
        await session.commit()
        return True


# ════════════════════════════════════════════════════════════
# Leads / ventas
# ════════════════════════════════════════════════════════════

async def registrar_lead(telefono: str, nombre: str = "", interes: str = "") -> dict:
    """Registra un lead nuevo o actualiza el interés si ya existe."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalars().first()
        if lead:
            if nombre:
                lead.nombre = nombre
            if interes:
                lead.interes = (lead.interes + " | " + interes) if lead.interes else interes
            await session.commit()
            return {"id": lead.id, "estado": lead.estado, "nuevo": False}
        lead = Lead(telefono=telefono, nombre=nombre, interes=interes, estado="nuevo")
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        logger.info(f"Lead nuevo #{lead.id} — {telefono} — {interes}")
        return {"id": lead.id, "estado": "nuevo", "nuevo": True}


async def calificar_lead(telefono: str, nuevo_estado: str) -> bool:
    """Actualiza el estado de un lead (nuevo, calificado, cerrado, perdido)."""
    async with async_session() as session:
        query = select(Lead).where(Lead.telefono == telefono)
        result = await session.execute(query)
        lead = result.scalars().first()
        if not lead:
            return False
        lead.estado = nuevo_estado
        await session.commit()
        return True


# ════════════════════════════════════════════════════════════
# Búsqueda en /knowledge
# ════════════════════════════════════════════════════════════

def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
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

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


# ════════════════════════════════════════════════════════════
# Utilidades
# ════════════════════════════════════════════════════════════

def extraer_telefono_email(texto: str) -> dict:
    """Extrae teléfono y email del texto si los hay."""
    tel = re.search(r"(\+?\d[\d \-\.]{7,}\d)", texto)
    email = re.search(r"[\w\.\-]+@[\w\.\-]+\.\w+", texto)
    return {
        "telefono": tel.group(0) if tel else None,
        "email": email.group(0) if email else None,
    }
