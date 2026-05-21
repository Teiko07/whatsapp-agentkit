import os
import yaml
import logging

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


def registrar_lead(telefono: str, datos: dict) -> str:
    logger.info(f"Lead calificado — tel:{telefono} datos:{datos}")
    return "Lead registrado correctamente."
