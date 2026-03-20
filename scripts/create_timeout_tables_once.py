"""기존 승인 길드의 타임아웃 테이블을 1회 생성하는 스크립트."""

from utils.function import get_conn, ensure_timeout_table


def main():
    created = 0
    scanned = 0

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT guild_id FROM guilds WHERE approved = 1")
        guild_ids = [row[0] for row in cur.fetchall()]

        for guild_id in guild_ids:
            scanned += 1
            ensure_timeout_table(cur, int(guild_id))
            created += 1

        conn.commit()

    print(f"[DONE] scanned={scanned}, ensured_tables={created}")


if __name__ == "__main__":
    main()
