import os
import yaml
import logging
from anthropic import AsyncAnthropic
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), override=True)
logger = logging.getLogger("agentkit")

client = AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODELO = "claude-haiku-4-5-20251001"

TOOLS = [
    {
        "name": "registrar_lead",
        "description": (
            "Registra un lead en el CRM. Llama esta función SOLO cuando el cliente haya "
            "confirmado explícitamente su nombre Y su número de teléfono. No la llames "
            "si solo tienes uno de los dos datos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {
                    "type": "string",
                    "description": "Nombre del cliente tal como lo ha dicho"
                },
                "telefono": {
                    "type": "string",
                    "description": "Número de teléfono del cliente (el que usa para WhatsApp)"
                },
                "interes": {
                    "type": "string",
                    "description": "Resumen de lo que busca: zona, tipo de propiedad, presupuesto"
                }
            },
            "required": ["nombre", "telefono"]
        }
    }
]


def cargar_config_prompts() -> dict:
    try:
        with open("config/prompts.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        logger.error("config/prompts.yaml no encontrado")
        return {}


def cargar_system_prompt() -> str:
    config = cargar_config_prompts()
    return config.get("system_prompt", "Eres un asistente útil. Responde en español.")


def obtener_mensaje_error() -> str:
    config = cargar_config_prompts()
    return config.get("error_message", "Lo siento, estoy teniendo problemas técnicos. Por favor intenta de nuevo en unos minutos.")


def obtener_mensaje_fallback() -> str:
    config = cargar_config_prompts()
    return config.get("fallback_message", "Disculpa, no entendí tu mensaje. ¿Podrías reformularlo?")


async def _ejecutar_herramienta(nombre: str, parametros: dict, telefono_cliente: str) -> str:
    if nombre == "registrar_lead":
        from agent.tools import registrar_lead_n8n
        return await registrar_lead_n8n(
            telefono=telefono_cliente,
            nombre=parametros.get("nombre", ""),
            interes=parametros.get("interes", "")
        )
    return "Herramienta no encontrada."


async def generar_respuesta(mensaje: str, historial: list[dict], telefono: str = "unknown") -> str:
    if not mensaje or len(mensaje.strip()) < 2:
        return obtener_mensaje_fallback()

    system_prompt = cargar_system_prompt()

    mensajes = []
    for msg in historial:
        mensajes.append({"role": msg["role"], "content": msg["content"]})
    mensajes.append({"role": "user", "content": mensaje})

    try:
        response = await client.messages.create(
            model=MODELO,
            max_tokens=512,
            system=system_prompt,
            tools=TOOLS,
            messages=mensajes
        )

        # Claude quiere usar una herramienta (ej: registrar_lead)
        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    resultado = await _ejecutar_herramienta(block.name, block.input, telefono)
                    logger.info(f"Tool {block.name} ejecutado: {resultado}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": resultado
                    })

            # Devolver resultado al modelo para que genere la respuesta final
            mensajes.append({"role": "assistant", "content": response.content})
            mensajes.append({"role": "user", "content": tool_results})

            response2 = await client.messages.create(
                model=MODELO,
                max_tokens=512,
                system=system_prompt,
                tools=TOOLS,
                messages=mensajes
            )
            respuesta = response2.content[0].text
            logger.info(f"Haiku+tool ({response.usage.input_tokens}in): {respuesta[:60]}...")
        else:
            respuesta = response.content[0].text
            logger.info(f"Haiku ({response.usage.input_tokens}in/{response.usage.output_tokens}out): {respuesta[:60]}...")

        return respuesta

    except Exception as e:
        logger.error(f"Error Claude API: {e}")
        return obtener_mensaje_error()
