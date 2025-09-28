import psycopg2
from utils.cache import settings_cache
from datetime import datetime, timedelta
import os
import platform
from contextlib import closing
import aiohttp
from urllib.parse import quote, unquote

API_TOKEN = os.getenv("API_TOKEN")

# 운영체제 확인
if platform.system() == "Windows":
    host = "3.37.78.228"  # 외부 접속용
else:
    host = "localhost"    # 리눅스 내부 접속용

DB_CONFIG = {
    "host": host,
    "port": 5432,
    "dbname": "kadanbot",
    "user": "kadan",
    "password": "wndnwkdkr8"
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG)

# -----------------
# Guilds 관련 함수
# -----------------
LOSTARK_SERVERS = [
    "카단", "카제로스", "니나브", "아브렐슈드",
    "실리안", "카마인", "아만", "루페온",
]

def add_guild(guild_id: int, user_id: int, server: str):
    if server not in LOSTARK_SERVERS:
        raise ValueError(f"❌ 유효하지 않은 서버: {server}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO guilds (guild_id, registered_by, approved, server, created_at)
            VALUES (%s, %s, 0, %s, %s)
            ON CONFLICT (guild_id)
            DO UPDATE SET registered_by=EXCLUDED.registered_by,
                          approved=0,
                          server=EXCLUDED.server,
                          created_at=EXCLUDED.created_at
            """,
            (guild_id, user_id, server, datetime.utcnow() + timedelta(hours=9))
        )
        conn.commit()

def approve_guild(guild_id: int, admin_id: int):
    with get_conn() as conn, conn.cursor() as cur:
        now = datetime.utcnow() + timedelta(hours=9)

        # 1️⃣ guild 승인 처리
        cur.execute(
            "UPDATE guilds SET approved = 1, approved_by = %s, created_at = %s WHERE guild_id = %s",
            (admin_id, now, guild_id)
        )

        # 2️⃣ 인증 관련 테이블 자동 생성
        tables_sql = [
            f"""
            CREATE TABLE IF NOT EXISTS auth_accounts_{guild_id} (
                id SERIAL PRIMARY KEY,
                discord_user_id BIGINT NOT NULL,
                stove_member_no VARCHAR NOT NULL,
                nickname VARCHAR,
                is_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                verified_at TIMESTAMP,
                expired_at TIMESTAMP
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS auth_sub_accounts_{guild_id} (
                id SERIAL PRIMARY KEY,
                discord_user_id BIGINT NOT NULL,
                sub_number INT NOT NULL,
                stove_member_no VARCHAR,
                nickname VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS deleted_auth_accounts_{guild_id} (
                id INT,
                discord_user_id BIGINT,
                stove_member_no VARCHAR,
                nickname VARCHAR,
                is_verified BOOLEAN,
                created_at TIMESTAMP,
                verified_at TIMESTAMP,
                deleted_at TIMESTAMP,
                retain_until TIMESTAMP
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS deleted_auth_sub_accounts_{guild_id} (
                id INT,
                discord_user_id BIGINT,
                sub_number INT,
                stove_member_no VARCHAR,
                nickname VARCHAR,
                created_at TIMESTAMP,
                deleted_at TIMESTAMP,
                retain_until TIMESTAMP
            )
            """
        ]

        for sql in tables_sql:
            cur.execute(sql)

        conn.commit()

def reject_guild(guild_id: int, admin_id: int):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE guilds SET approved = -1, approved_by = %s, created_at = %s WHERE guild_id = %s",
            (admin_id, datetime.utcnow() + timedelta(hours=9), guild_id)
        )
        conn.commit()

def is_approved(guild_id: int) -> bool:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT approved FROM guilds WHERE guild_id = %s", (guild_id,))
        row = cur.fetchone()
        return row and row[0] == 1

def get_setting_value(guild_id: int, key: str) -> str | None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE guild_id = %s AND key = %s", (guild_id, key))
        row = cur.fetchone()
        return row[0] if row else None

def get_all_settings() -> dict[int, dict[str, str]]:
    """DB 전체 settings + guilds.server 를 길드별 dict로 반환"""
    cache: dict[int, dict[str, str]] = {}

    with get_conn() as conn, conn.cursor() as cur:
        # ✅ settings 테이블
        cur.execute("SELECT guild_id, key, value FROM settings")
        for guild_id, key, value in cur.fetchall():
            if guild_id not in cache:
                cache[guild_id] = {}
            cache[guild_id][key] = value

        # ✅ guilds 테이블 (server 컬럼만)
        cur.execute("SELECT guild_id, server FROM guilds WHERE server IS NOT NULL")
        for guild_id, server in cur.fetchall():
            if guild_id not in cache:
                cache[guild_id] = {}
            cache[guild_id]["server"] = server

    return cache

def get_setting_cached(guild_id: int = None, key: str = None):
    """
    캐시에서 설정값 가져오기
    """
    if guild_id is None and key is None:
        return settings_cache
    if key is None:
        return settings_cache.get(guild_id, {})
    return settings_cache.get(guild_id, {}).get(key)

def set_setting(guild_id: int, key: str, value: str, changed_by: int, reason: str = "edit"):
    """설정 저장 + 로그 기록 (DB + 캐시 동시에 업데이트)"""
    now = datetime.utcnow() + timedelta(hours=9)
    with get_conn() as conn, conn.cursor() as cur:
        # 기존 값 확인
        cur.execute("SELECT value FROM settings WHERE guild_id = %s AND key = %s", (guild_id, key))
        row = cur.fetchone()
        old_value = row[0] if row else None

        if row:
            # UPDATE
            cur.execute("""
                UPDATE settings
                SET value = %s, changed_by = %s, updated_at = %s
                WHERE guild_id = %s AND key = %s
            """, (value, changed_by, now, guild_id, key))
            reason = reason or "edit"
        else:
            # INSERT
            cur.execute("""
                INSERT INTO settings (guild_id, key, value, changed_by, updated_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (guild_id, key, value, changed_by, now))
            reason = reason or "create"

        # 로그 기록
        cur.execute("""
            INSERT INTO setting_logs (guild_id, key, old_value, new_value, changed_by, reason, changed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (guild_id, key, old_value, value, changed_by, reason, now))

        conn.commit()

    # ✅ 캐시 업데이트
    if guild_id not in settings_cache:
        settings_cache[guild_id] = {}
    settings_cache[guild_id][key] = value

def block_user(guild_id: int, data, reason: str | None, blocked_by: int):
    """
    유저/닉네임/discord_id를 입력받아 관련된 모든 인증/삭제 인증 정보를 조회 후
    blocked_users 테이블에 차단을 등록한다.
    """
    import discord
    inserts: list[tuple[str, str]] = []

    with get_conn() as conn, conn.cursor() as cur:
        discord_id = None
        nickname = None

        # 1️⃣ 입력값 판별
        if isinstance(data, discord.Member):
            discord_id = str(data.id)
        elif isinstance(data, int) or (isinstance(data, str) and data.isdigit()):
            discord_id = str(data)
        else:
            nickname = str(data)

        # 2️⃣ Discord ID 기준 조회
        if discord_id:
            inserts.append(("discord_id", discord_id))

            cur.execute(
                f"""
                SELECT stove_member_no, nickname FROM auth_accounts_{guild_id} WHERE discord_user_id = %s
                UNION ALL
                SELECT stove_member_no, nickname FROM deleted_auth_accounts_{guild_id} WHERE discord_user_id = %s
                """,
                (discord_id, discord_id)
            )
            for stove_member_no, nick in cur.fetchall():
                if stove_member_no:
                    inserts.append(("memberNo", stove_member_no))
                if nick:
                    inserts.append(("nickname", nick))

            cur.execute(
                f"""
                SELECT stove_member_no, nickname FROM auth_sub_accounts_{guild_id} WHERE discord_user_id = %s
                UNION ALL
                SELECT stove_member_no, nickname FROM deleted_auth_sub_accounts_{guild_id} WHERE discord_user_id = %s
                """,
                (discord_id, discord_id)
            )
            for sub_member_no, sub_nick in cur.fetchall():
                if sub_member_no:
                    inserts.append(("memberNo", sub_member_no))
                if sub_nick:
                    inserts.append(("nickname", sub_nick))

        # 3️⃣ 닉네임 기준 조회
        if nickname:
            inserts.append(("nickname", nickname))

            cur.execute(
                f"""
                SELECT discord_user_id, stove_member_no FROM auth_accounts_{guild_id} WHERE nickname = %s
                UNION ALL
                SELECT discord_user_id, stove_member_no FROM deleted_auth_accounts_{guild_id} WHERE nickname = %s
                """,
                (nickname, nickname)
            )
            for did, stove_member_no in cur.fetchall():
                if did:
                    inserts.append(("discord_id", str(did)))
                if stove_member_no:
                    inserts.append(("memberNo", stove_member_no))

            cur.execute(
                f"""
                SELECT discord_user_id, stove_member_no FROM auth_sub_accounts_{guild_id} WHERE nickname = %s
                UNION ALL
                SELECT discord_user_id, stove_member_no FROM deleted_auth_sub_accounts_{guild_id} WHERE nickname = %s
                """,
                (nickname, nickname)
            )
            for did, stove_member_no in cur.fetchall():
                if did:
                    inserts.append(("discord_id", str(did)))
                if stove_member_no:
                    inserts.append(("memberNo", stove_member_no))

        # ✅ 중복 제거
        inserts = list(set(inserts))
        if not inserts:
            return [], []

        # 4️⃣ 이미 차단된 값 확인
        params = [guild_id]
        conditions = []
        for dtype, value in inserts:
            conditions.append("(data_type = %s AND value = %s)")
            params.extend([dtype, str(value)])

        sql = f"""
            SELECT data_type, value
            FROM blocked_users
            WHERE guild_id = %s AND unblocked_at IS NULL
            AND ({' OR '.join(conditions)})
        """
        cur.execute(sql, tuple(params))
        already_blocked = cur.fetchall()

        already_set = set(already_blocked)
        new_blocks = [item for item in inserts if item not in already_set]

        # 5️⃣ 새로 차단할 값만 일괄 insert
        if new_blocks:
            cur.executemany(
                """INSERT INTO blocked_users
                   (guild_id, data_type, value, reason, created_at, blocked_by)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [
                    (guild_id, dtype, str(value), reason, datetime.utcnow(), blocked_by)
                    for dtype, value in new_blocks
                ]
            )

        conn.commit()

    return new_blocks, already_blocked

def is_account_duplicate(guild_id: int, discord_id: int, member_no: str, nicknames: list[str]) -> list[tuple]:
    results = []
    with closing(get_conn()) as conn, closing(conn.cursor()) as cur:
        cur.execute(
            f"""
            SELECT stove_member_no, nickname
            FROM auth_accounts_{guild_id}
            WHERE discord_user_id = %s OR stove_member_no = %s OR nickname = ANY(%s)
            """,
            (discord_id, member_no, nicknames)
        )
        results.extend(cur.fetchall())

        cur.execute(
            f"""
            SELECT stove_member_no, nickname
            FROM auth_sub_accounts_{guild_id}
            WHERE discord_user_id = %s OR stove_member_no = %s OR nickname = ANY(%s)
            """,
            (discord_id, member_no, nicknames)
        )
        results.extend(cur.fetchall())
    return results

def is_memberno_duplicate(guild_id: int, member_no: str) -> list[tuple]:
    """본계정 + 부계정 테이블 전부에서 memberNo 중복 확인"""
    results = []
    with get_conn() as conn, conn.cursor() as cur:
        # 본계정 테이블
        cur.execute(
            f"SELECT stove_member_no, nickname FROM auth_accounts_{guild_id} WHERE stove_member_no = %s",
            (member_no,)
        )
        results.extend(cur.fetchall())

        # 부계정 테이블
        cur.execute(
            f"SELECT stove_member_no, nickname FROM auth_sub_accounts_{guild_id} WHERE stove_member_no = %s",
            (member_no,)
        )
        results.extend(cur.fetchall())

    return results

def get_user_blocked(guild_id: int, discord_id: int, member_no: str, nicknames: list[str]) -> list[dict]:
    blocked = []
    with get_conn() as conn, conn.cursor() as cur:
        placeholders = ", ".join(["%s"] * len(nicknames)) if nicknames else "NULL"
        cur.execute(
            f"""
            SELECT guild_id, data_type, value, reason, created_at, blocked_by
            FROM blocked_users
            WHERE guild_id = %s
            AND (
                (data_type='discord_id' AND value = %s)
                OR (data_type='memberNo' AND value = %s)
                OR (data_type='nickname' AND value IN ({placeholders}))
            )
            AND unblocked_at IS NULL
            """,
            (guild_id, str(discord_id), member_no, *nicknames)
        )
        rows = cur.fetchall()

    for r in rows:
        blocked.append({
            "guild_id": r[0],
            "data_type": r[1],
            "value": r[2],
            "reason": r[3],
            "created_at": r[4],
            "blocked_by": r[5]
        })
    return blocked

def save_main_account(guild_id: int, discord_id: int, member_no: str, nickname: str):
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO auth_accounts_{guild_id}
                (discord_user_id, stove_member_no, nickname, is_verified, verified_at)
            VALUES (%s, %s, %s, TRUE, NOW())
            """,
            (discord_id, member_no, nickname)
        )
        conn.commit()

def save_sub_account(guild_id: int, discord_id: int, stove_member_no: str, nickname: str) -> int:
    """
    부계정 등록 & sub_number 발급
    :return: 새로 등록된 부계정의 sub_number
    """
    table = f"auth_sub_accounts_{guild_id}"
    with get_conn() as conn, conn.cursor() as cur:
        # 현재 최대 sub_number 조회
        cur.execute(f"SELECT COALESCE(MAX(sub_number), 0) FROM {table} WHERE discord_user_id = %s", (discord_id,))
        last_num = cur.fetchone()[0] or 0
        new_num = last_num + 1

        # 새 부계정 INSERT
        cur.execute(
            f"""
            INSERT INTO {table} (discord_user_id, stove_member_no, nickname, sub_number, created_at)
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (discord_id, stove_member_no, nickname, new_num)
        )
        conn.commit()

        return new_num

def has_sub_accounts(guild_id: int, discord_id: int) -> bool:
    """해당 유저가 부계정을 보유 중인지 확인"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM auth_sub_accounts_{guild_id} WHERE discord_user_id = %s LIMIT 1",
            (discord_id,)
        )
        return cur.fetchone() is not None

def build_final_nickname(guild_id: int, discord_id: int, base_nick: str, is_main: bool) -> str:
    import re
    """
    최종 닉네임 생성 규칙:
    - 본계정만 있으면: 본계정 닉 그대로 (붙어 있던 태그도 제거)
    - 본계정 + 부계정 있으면: 닉 끝에 ' | 부계정O' (중복 방지)
    - 부계정이면: 닉 끝에 항상 ' | 부계정O' (중복 방지)
    """
    tag = "부계정O"
    pattern = re.compile(r"\s*\|\s*부계정O\s*$", re.IGNORECASE)

    def add_tag(nick: str) -> str:
        return nick if pattern.search(nick) else f"{nick} | {tag}"

    def remove_tag(nick: str) -> str:
        return pattern.sub("", nick)

    if is_main:
        if has_sub_accounts(guild_id, discord_id):
            return add_tag(base_nick)
        else:
            return remove_tag(base_nick)
    else:
        return add_tag(base_nick)
    
def is_main_registered(guild_id: int, discord_id: int) -> bool:
    """해당 유저가 본계정을 등록했는지 확인"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT 1 FROM auth_accounts_{guild_id} WHERE discord_user_id = %s AND is_verified = TRUE LIMIT 1",
            (discord_id,)
        )
        return cur.fetchone() is not None

def unblock_user(blocked_entries: list[dict], unblocked_by: int) -> int:
    with get_conn() as conn, conn.cursor() as cur:
        now = datetime.utcnow()  # ✅ PostgreSQL TIMESTAMP와 호환
        count = 0
        for entry in blocked_entries:
            cur.execute(
                """
                UPDATE blocked_users
                SET unblocked_at = %s, unblocked_by = %s
                WHERE guild_id = %s AND data_type = %s AND value = %s AND unblocked_at IS NULL
                """,
                (now, str(unblocked_by), entry["guild_id"], entry["data_type"], entry["value"])
            )
            if cur.rowcount > 0:
                count += 1
        conn.commit()
    return count

def get_main_account_memberno(guild_id: int, discord_id: int) -> str | None:
    """해당 유저의 본계정 stove_member_no 반환 (없으면 None)"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT stove_member_no FROM auth_accounts_{guild_id} "
            f"WHERE discord_user_id = %s AND is_verified = TRUE LIMIT 1",
            (discord_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

async def fetch_character_list(member_no: str, guild_id: int) -> list[dict] | None:
    """
    Lost Ark API: 주어진 memberNo로 해당 서버의 캐릭터 리스트 조회
    """
    url_list = "https://lostark.game.onstove.com/board/IsCharacterList"
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession() as session:
        # 1) encryptMemberNo 가져오기
        try:
            async with session.post(url_list, data={"memberNo": member_no}, headers=headers) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                encrypt_member_no = data.get("encryptMemberNo")
                if not encrypt_member_no:
                    return None
        except Exception:
            return None

        # 2) 전투정보실 URL 가져오기
        try:
            url_profile = f"https://lostark.game.onstove.com/Profile/Member?id={quote(encrypt_member_no)}"
            async with session.get(url_profile, headers=headers, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                final_url = str(resp.url)
                main_char_encoded = final_url.split("/")[-1]
                main_char = unquote(main_char_encoded)
        except Exception:
            return None

        # 3) 공식 API 호출 (siblings)
        try:
            url_api = f"https://developer-lostark.game.onstove.com/characters/{quote(main_char)}/siblings"
            api_headers = {
                "Authorization": f"bearer {API_TOKEN}",
                "User-Agent": "Mozilla/5.0"
            }
            async with session.get(url_api, headers=api_headers) as resp:
                if resp.status != 200:
                    return None
                characters = await resp.json()
        except Exception:
            return None

    if not characters:
        return None

    # 4) 서버 필터링
    server = get_setting_cached(guild_id, "server")
    if server:
        characters = [c for c in characters if c.get("ServerName") == server]

    return characters or None

def get_main_account_nickname(guild_id: int, discord_id: int) -> str | None:
    """
    길드의 본계정 테이블에서 현재 등록된 닉네임 조회
    """
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT nickname FROM auth_accounts_{guild_id} "
            f"WHERE discord_user_id = %s AND is_verified = TRUE LIMIT 1",
            (discord_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None

def update_main_account_nickname(
    guild_id: int,
    discord_id: int,
    new_nickname: str,
) -> int:
    """본계정 닉네임을 새 값으로 업데이트"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"UPDATE auth_accounts_{guild_id} "
            f"SET nickname = %s "
            f"WHERE discord_user_id = %s AND is_verified = TRUE",
            (new_nickname, discord_id)
        )
        conn.commit()
        return cur.rowcount

def get_sub_accounts(guild_id: int, discord_id: int) -> list[tuple[int, str]]:
    """
    유저의 부계정 목록 조회
    :return: [(sub_number, nickname), ...]
    """
    table = f"auth_sub_accounts_{guild_id}"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT sub_number, nickname FROM {table} "
            f"WHERE discord_user_id = %s ORDER BY sub_number ASC",
            (discord_id,)
        )
        return cur.fetchall()  # [(sub_number, nickname), ...]

def delete_main_account(guild_id: int, discord_id: int) -> tuple[str | None, list[tuple[int, str]]]:
    """
    본계정 + 모든 부계정 → deleted 테이블 이관
    :return: (본계정 닉네임, 부계정 리스트[(sub_number, nickname), ...])
    """
    table_main = f"auth_accounts_{guild_id}"
    table_sub = f"auth_sub_accounts_{guild_id}"
    deleted_main = f"deleted_auth_accounts_{guild_id}"
    deleted_sub = f"deleted_auth_sub_accounts_{guild_id}"

    with get_conn() as conn, conn.cursor() as cur:
        # 🔹 본계정 조회 & 이관
        cur.execute(
            f"SELECT id, discord_user_id, stove_member_no, nickname, is_verified, created_at, verified_at, expired_at "
            f"FROM {table_main} WHERE discord_user_id=%s",
            (discord_id,)
        )
        main_row = cur.fetchone()
        main_nick = None
        if main_row:
            main_nick = main_row[3]  # nickname
            cur.execute(
                f"""
                INSERT INTO {deleted_main}
                (id, discord_user_id, stove_member_no, nickname,
                 is_verified, created_at, verified_at, deleted_at, retain_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_DATE + INTERVAL '180 days')
                """,
                main_row[:-1]  # expired_at 제외
            )
            cur.execute(f"DELETE FROM {table_main} WHERE discord_user_id=%s", (discord_id,))

        # 🔹 부계정 조회 & 이관
        cur.execute(
            f"SELECT id, discord_user_id, sub_number, stove_member_no, nickname, created_at "
            f"FROM {table_sub} WHERE discord_user_id=%s",
            (discord_id,)
        )
        sub_rows = cur.fetchall()
        sub_list = []
        for row in sub_rows:
            sub_number, nickname = row[2], row[4]
            sub_list.append((sub_number, nickname))
            cur.execute(
                f"""
                INSERT INTO {deleted_sub}
                (id, discord_user_id, sub_number, stove_member_no,
                 nickname, created_at, deleted_at, retain_until)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_DATE + INTERVAL '180 days')
                """,
                row
            )
        cur.execute(f"DELETE FROM {table_sub} WHERE discord_user_id=%s", (discord_id,))
        conn.commit()

        return main_nick, sub_list

def delete_sub_account(guild_id: int, discord_id: int, sub_number: int) -> str | None:
    """
    특정 부계정만 deleted 테이블로 이관 + sub_number 재정렬
    :return: 삭제된 닉네임 (없으면 None)
    """
    table_sub = f"auth_sub_accounts_{guild_id}"
    deleted_sub = f"deleted_auth_sub_accounts_{guild_id}"

    with get_conn() as conn, conn.cursor() as cur:
        # 🔹 대상 부계정 조회
        cur.execute(
            f"SELECT id, discord_user_id, sub_number, stove_member_no, nickname, created_at "
            f"FROM {table_sub} WHERE discord_user_id=%s AND sub_number=%s",
            (discord_id, sub_number)
        )
        row = cur.fetchone()
        if not row:
            return None

        deleted_nick = row[4]

        # 🔹 삭제 테이블로 이관
        cur.execute(
            f"""
            INSERT INTO {deleted_sub}
            (id, discord_user_id, sub_number, stove_member_no,
             nickname, created_at, deleted_at, retain_until)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_DATE + INTERVAL '180 days')
            """,
            row
        )
        cur.execute(
            f"DELETE FROM {table_sub} WHERE discord_user_id=%s AND sub_number=%s",
            (discord_id, sub_number)
        )

        # 🔹 sub_number 재정렬
        cur.execute(
            f"SELECT id FROM {table_sub} WHERE discord_user_id=%s ORDER BY sub_number ASC",
            (discord_id,)
        )
        subs = cur.fetchall()
        for new_num, (id_,) in enumerate(subs, start=1):
            cur.execute(f"UPDATE {table_sub} SET sub_number=%s WHERE id=%s", (new_num, id_))

        conn.commit()
        return deleted_nick

def get_sub_accounts_membernos(guild_id: int, discord_id: int) -> list[str]:
    """
    특정 유저의 부계정 stove_member_no 리스트 반환
    """
    table = f"auth_sub_accounts_{guild_id}"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            f"SELECT stove_member_no FROM {table} "
            f"WHERE discord_user_id = %s AND stove_member_no IS NOT NULL",
            (discord_id,)
        )
        rows = cur.fetchall()
        return [r[0] for r in rows if r[0]]
    
async def fetch_character_list_by_nickname(nickname: str) -> list[dict] | None:
    """
    Lost Ark API: 닉네임으로 siblings 조회 (memberNo 없는 경우 fallback)
    """
    url_api = f"https://developer-lostark.game.onstove.com/characters/{quote(nickname)}/siblings"
    headers = {
        "Authorization": f"bearer {API_TOKEN}",
        "User-Agent": "Mozilla/5.0"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url_api, headers=headers) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception:
        return None
    
    