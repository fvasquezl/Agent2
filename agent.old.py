import json

import psycopg
from groq import Groq
from groq.types.chat import ChatCompletionMessageParam

from agent1.long_term_memory import LongTermMemory
from agent1.memory import SimpleMemory
from agent1.tools import Tool
from agent1.tools.memory import crear_herramientas_memoria

SYSTEM_PROMPT = """
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


class Agent:
    def __init__(
        self,
        client: Groq,
        model: str,
        tools: list[Tool],
        memory: SimpleMemory,
        ltm: LongTermMemory,
        user_id: str,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.client = client
        self.model = model
        self.memory = memory
        self.ltm = ltm
        self.user_id = user_id
        self.system_prompt = system_prompt

        # El prompt menciona guardar_memoria_largo_plazo, así que el agente siempre la incluye
        all_tools = [*tools, *crear_herramientas_memoria(ltm, user_id)]
        self.tools = {tool.name: tool for tool in all_tools}
        self.schemas = [tool.schema() for tool in all_tools]

    def _build_system_prompt(self) -> str:
        # Llena el hueco {memories_text} de la plantilla con las memorias actuales
        try:
            memories = self.ltm.get_long_term_memories(self.user_id)
            memories_text = self.ltm.format_memories(memories)
        except psycopg.Error as e:
            print("Error al cargar las memorias de largo plazo", e)
            memories_text = "(no fue posible cargar las memorias)"
        return self.system_prompt.format(memories_text=memories_text)

    def chat(self, user_text: str) -> str:
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": self._build_system_prompt()},
            *self.memory.messages(),
            {"role": "user", "content": user_text},
        ]

        while True:
            resp = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.schemas
            )
            msg = resp.choices[0].message

            # Si no hay llamados a herramientas, ya tenemos la respuesta final
            if not msg.tool_calls:
                answer = msg.content or ""
                self.memory.add("user", user_text)
                self.memory.add("assistant", answer)
                return answer

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

            # El resultado de cada herramienta lo recibirá el modelo en la siguiente vuelta
            for tool_call in msg.tool_calls:
                result = self._run_tool(
                    tool_call.function.name, tool_call.function.arguments
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            result
                            if isinstance(result, str)
                            else json.dumps(result, ensure_ascii=False)
                        ),
                    }
                )

    def _run_tool(self, name: str, arguments: str | None) -> object:
        tool = self.tools.get(name)
        if tool is None:
            print(f"Se intentó llamar a una herramienta desconocida {name}")
            return {"error": f"Herramienta desconocida: {name}"}

        try:
            return tool.func(**json.loads(arguments or "{}"))
        except (json.JSONDecodeError, TypeError) as e:
            return {"error": f"Argumentos inválidos para {name}: {e}"}
