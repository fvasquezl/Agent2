import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from groq import Groq
from groq.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

from long_term_memory import LongTermMemory
from simple_memory import SimpleMemory

load_dotenv()

MEMORY_MAX_MESSAGES = 10

api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=api_key)
memory = SimpleMemory(max_messages=MEMORY_MAX_MESSAGES)
now = datetime.now(ZoneInfo("America/Tijuana"))

DATABASE_URL = os.environ.get("DATABASE_URL")
ltm = LongTermMemory(database_url=DATABASE_URL)
memories = ltm.get_long_term_memories(user_id="12345")
memories_text = ltm.format_memories(memories)

SYSTEM_PROMPT = f"""
# ROL
Eres un asistente que habla en español y responde de manera muy breve y concisa.

# REGLAS
- Por cada mensaje que envia el usuario, debes evaluar si tiene información inportante
  o personal (nombre, apellido, edad, fecha de nacimiento y otra información especifica del usuario, asi como
  preferencias, hábitos, objetivos, eventos importantes).
  De ser así, utiliza la herramienta llamada **guardar_memoria_largo_plazo** para guardar dicha información
  en memoria de largo plazo.
- Debes responder al usuario de manera natural y amigable. Aunque guardes información, tu respuesta no debe indicar
  dicha accion.
- Utiliza memorias almacenadas para dar respuestas personalizadas y con contexto relevante.
- Considera la fecha y hora de las memorias obtenidas. Tus respuestas deben ser actualizadas.
- Redacta tus respuestas segun preferencias del usuario e interacciones anteriores.
- Nunca almacenes información sensible como nombres de usuario, contraseñas, tarjetas de crédito, o información de pagos

# HERRAMIENTAS

# guardar_memoria_largo_plazo
- Utiliza esta herramienta para almacenar información importante del usuario que debas manener para futuras
  interacciones en memoria de largo plazo

# MEMORIAS
## Memorias importantes recientes
- A continuación aparece una lista de las memorias almacenadas (puede estar vacía).

== INICIO DE MEMORIAS
{memories_text}
== FIN DE MEMORIAS

## Guía para el uso de memorias:
- Prioriza los mensajes recientes
- Referencía las memorias entre ellas para mantener consistencia en tus respuestas.
  Por ejemplo, si el usuario comparte preferencias que hacen conflicto con el tiempo, clarifica o adáptate.

- Usa las herramientas disponibles cuando la pregunta lo requiera.
"""

TOOLS: list[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "guardar_memoria_largo_plazo",
            "description": (
                "Utiliza esta herramienta cual el usuario haya dicho algo importante que consideres que se debe almacenar como memoria de largo plazo"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "memory": {
                        "type": "string",
                        "description": "La memoria a almacenar",
                    },
                },
                "required": ["memory"],
            },
        },
    },
]

print("Agente de IA")


def process_response(
    client: Groq, memory_messages: list[ChatCompletionMessageParam], user_text: str
):
    # Obtener la memoria
    messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]
    messages.extend(memory_messages)
    messages.append({"role": "user", "content": user_text})

    while True:
        resp = client.chat.completions.create(
            model="openai/gpt-oss-120b", messages=messages, tools=TOOLS
        )

        msg = resp.choices[0].message

        # Si no hay llamados a herramientas, entonces ya regresamos la respuesta
        if not getattr(msg, "tool_calls", None):
            return msg.content or ""

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            }
        )

        for tool_call in msg.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")

            if name == "guardar_memoria_largo_plazo":
                ltm.insert_long_term_memory(
                    user_id="12345", memory=args.get("memory", "")
                )
                result = "Memoria se guardo correctamente"
            else:
                print(f"Se intentó llamar a una herramienta desconocida {name}")
                result = {"error": f"Herramienta desconocida: {name}"}

            # Agregar a los mensajes el resultao del llamado de la herramienta.
            # Esto lo recibirá el modelo al continuar la iteración
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )


while True:
    user_text = input("Tú: ").strip()
    if not user_text:
        continue

    if user_text.lower() in ("exit", "salir"):
        print("Hasta luego!")
        break

    assistant_text = process_response(client, memory.messages(), user_text)
    print(f"Asistente: {assistant_text}")

    # Actualizar la memoria
    memory.add("user", user_text)
    memory.add("assistant", assistant_text)
