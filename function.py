import discord
import aiohttp
import psycopg2
from datetime import datetime, timedelta
import platform

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
# 운영 서버 및 역할 ID
OPERATING_GUILD_ID = 743375510003777618
EXCHANGE_ROLE_ID = 864114840876482581

def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def get_bot_token() -> str | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'bot_token'")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_setting(key: str) -> str | None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


def get_api_key() -> str | None:
    return get_setting("api_key")


def get_user_sub_count(discord_id: int) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM sub_accounts WHERE discord_id = %s AND delete_time IS NULL",
        (str(discord_id),)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count


def get_max_subs() -> int:
    value = get_setting("max_subs")
    return int(value) if value else 1


def has_exchange_role(bot: discord.Bot, discord_id: int) -> bool:
    guild = bot.get_guild(OPERATING_GUILD_ID)
    if not guild:
        return False
    member = guild.get_member(discord_id)
    if not member:
        return False
    return any(role.id == EXCHANGE_ROLE_ID for role in member.roles)


async def check_lostark_nickname(nickname: str) -> bool:
    api_key = get_api_key()
    if not api_key:
        return False

    url = f"https://developer-lostark.game.onstove.com/characters/{nickname}/siblings"
    headers = {
        "accept": "application/json",
        "authorization": f"bearer {api_key}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                try:
                    data = await resp.json()
                    return bool(data)
                except aiohttp.ContentTypeError:
                    return False
            else:
                return False


def insert_sub_account(discord_id: int, main_nick: str, sub_nick: str, sub_num: int) -> bool:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM sub_accounts 
            WHERE discord_id = %s AND sub_nick = %s AND delete_time IS NULL
        """, (str(discord_id), sub_nick))
        if cursor.fetchone():
            return False

        cursor.execute("""
            INSERT INTO sub_accounts (discord_id, main_nick, sub_nick, sub_num, register_time)
            VALUES (%s, %s, %s, %s, %s)
        """, (str(discord_id), main_nick, sub_nick, sub_num, datetime.utcnow() + timedelta(hours=9)))
        conn.commit()
        return True
    except Exception as e:
        print(f"[❌ DB insert_sub_account 에러] {type(e).__name__}: {e}")
        return False
    finally:
        conn.close()


def get_server_main_nick(bot: discord.Bot, discord_id: int) -> str | None:
    guild = bot.get_guild(OPERATING_GUILD_ID)
    if not guild:
        return None
    member = guild.get_member(discord_id)
    if not member:
        return None
    return member.nick or member.global_name


def get_main_nick(discord_id: int) -> str | None:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT main_nick FROM sub_accounts 
            WHERE discord_id = %s AND delete_time IS NULL 
            ORDER BY register_time ASC LIMIT 1
        """, (str(discord_id),))
        row = cursor.fetchone()
        return row[0] if row else None
    except:
        return None
    finally:
        conn.close()


def update_setting(key: str, value: str) -> bool:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("UPDATE settings SET value = %s WHERE key = %s", (value, key))
        conn.commit()
        return True
    except Exception as e:
        print(f"[❌ 설정 업데이트 실패] {e}")
        return False
    finally:
        conn.close()


def is_sub_nick_taken(sub_nick: str) -> bool:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 1 FROM sub_accounts
        WHERE sub_nick = %s AND delete_time IS NULL
    """, (sub_nick,))
    result = cursor.fetchone()
    conn.close()
    return result is not None


def get_all_sub_nicks() -> list[str]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sub_nick FROM sub_accounts
        WHERE delete_time IS NULL
    """)
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]


def save_foreign_sub_request(requester_id: int, target_id: int, sub_nick: str) -> bool:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO foreign_sub_requests (requester_id, target_id, requested_nick)
            VALUES (%s, %s, %s)
        """, (str(requester_id), str(target_id), sub_nick))
        conn.commit()
        return True
    except Exception as e:
        print(f"[❌ foreign_sub_requests insert 에러] {type(e).__name__}: {e}")
        return False
    finally:
        conn.close()


def update_foreign_request_status(requester_id: int, target_id: int, sub_nick: str, status: str) -> None:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE foreign_sub_requests
            SET status = %s, resolved_time = %s
            WHERE requester_id = %s AND target_id = %s AND requested_nick = %s
        """, (status, datetime.utcnow() + timedelta(hours=9), str(requester_id), str(target_id), sub_nick))
        conn.commit()
    except Exception as e:
        print(f"[❌ foreign_sub_requests 상태 업데이트 실패] {type(e).__name__}: {e}")
    finally:
        conn.close()


def get_user_sub_accounts(discord_id: int) -> list[str]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT sub_nick FROM sub_accounts
        WHERE discord_id = %s AND delete_time IS NULL
    """, (str(discord_id),))
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


async def get_lostark_account_set(nickname: str) -> set[str] | None:
    api_key = get_api_key()
    if not api_key:
        return None

    url = f"https://developer-lostark.game.onstove.com/characters/{nickname}/siblings"
    headers = {
        "accept": "application/json",
        "authorization": f"bearer {api_key}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            try:
                data = await resp.json()
                return set([c["CharacterName"] for c in data])
            except:
                return None


def delete_sub_account(discord_id: int, sub_nick: str) -> bool:
    try:
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT main_nick, sub_num, register_time, leave_time
            FROM sub_accounts
            WHERE discord_id = %s AND sub_nick = %s AND delete_time IS NULL
        """, (str(discord_id), sub_nick))
        row = cursor.fetchone()
        if not row:
            print("❌ 삭제할 부계정 정보를 찾을 수 없습니다.")
            return False

        main_nick, sub_num, register_time, leave_time = row

        cursor.execute("""
            INSERT INTO deleted_information (
                discord_id, main_nick, sub_nick, sub_num,
                register_time, leave_time, delete_time
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            str(discord_id), main_nick, sub_nick, sub_num,
            register_time, leave_time, datetime.utcnow() + timedelta(hours=9)
        ))

        cursor.execute("""
            DELETE FROM sub_accounts
            WHERE discord_id = %s AND sub_nick = %s
        """, (str(discord_id), sub_nick))

        cursor.execute("""
            UPDATE sub_accounts
            SET sub_num = sub_num - 1
            WHERE discord_id = %s AND sub_num > %s
        """, (str(discord_id), sub_num))

        conn.commit()
        return True

    except Exception as e:
        print(f"[❌ delete_sub_account 오류] {type(e).__name__}: {e}")
        return False

    finally:
        conn.close()


async def send_log_embed(
    bot: discord.Bot,
    user: discord.User | discord.Member,
    main_nick: str,
    title: str = "✅ 부계정 인증 완료"
):
    if title == '✅ 부계정 인증 완료':
        color = discord.Color.green()
    else:
        color = discord.Color.red()

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=datetime.utcnow() + timedelta(hours=9)
    )
    embed.add_field(name="유저", value=f"{user.mention} `{user.name}`", inline=False)
    embed.add_field(
        name="인증일시",
        value=(datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S"),
        inline=False
    )
    embed.add_field(name="계정", value=main_nick, inline=False)

    log_channel = bot.get_channel(1389312081764946053)
    if log_channel:
        await log_channel.send(embed=embed)
