import os

from dotenv import load_dotenv
from psycopg import Connection
from psycopg.rows import DictRow, dict_row


class LongTermMemory:
    def __init__(self, database_url):
        self.DATABASE_URL = database_url

    # Obtener la conexion de BD de Postgres (Supabase)
    def get_conn(self) -> Connection[DictRow]:
        return Connection[DictRow].connect(
            self.DATABASE_URL, row_factory=dict_row, prepare_threshold=None
        )

    # Obtener las memorias de largo plazo almacenadas actualmente
    def get_long_term_memories(self, user_id: str, limit: int = 20) -> list[DictRow]:
        with self.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                select created_at, memory
                from public.largo_plazo
                where user_id = %s
                order by created_at desc
                limit %s
                """,
                (user_id, limit),
            )
            return cur.fetchall()

    # Insertar una nueva memoria de largo plazo
    def insert_long_term_memory(self, user_id: str, memory: str) -> None:
        print(f"insercion de memoria llamada con {user_id}, {memory}")
        memory = (memory or "").strip()
        if not memory:
            return

        with self.get_conn() as conn, conn.cursor() as cur:
            cur.execute(
                """
                insert into public.largo_plazo(user_id,memory)
                values (%s,%s)
                """,
                (user_id, memory),
            )

    # Obtener las memorias  en formato de texto para el System Prompt
    def format_memories(self, memories: list[DictRow]) -> str:
        if not memories:
            return "(sin memorias)"

        lines = [
            f"- {m['created_at'].astimezone():%Y-%m-%d %H:%M}:{m['memory']}\n"
            for m in memories
        ]
        return "".join(lines)


if __name__ == "__main__":
    load_dotenv()
    ltm = LongTermMemory(database_url=os.environ.get("DATABASE_URL"))

    result = ltm.get_long_term_memories("1")
    print(result)

    # ltm.insert_long_term_memory("1", "memoria creada desde python")

    print(ltm.format_memories(result))
