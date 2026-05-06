from pathlib import Path

from psycopg import connect

from anchor.config import get_settings

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def main() -> None:
    settings = get_settings()
    with connect(settings.database_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
        )
        cur.execute("SELECT version FROM schema_migrations")
        applied = {row[0] for row in cur.fetchall()}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            sql = path.read_text().replace(
                "{{EMBEDDING_DIMENSION}}", str(settings.embedding_dimension)
            )
            cur.execute(sql)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.name,))
            print(f"applied {path.name}")


if __name__ == "__main__":
    main()
