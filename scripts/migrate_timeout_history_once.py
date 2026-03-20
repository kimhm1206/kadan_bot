"""레거시 차단 데이터 + 수동 리스트를 타임아웃 테이블로 이관하는 1회용 스크립트.

사용 예시:
  python scripts/migrate_timeout_history_once.py --guild-id 1234567890
  python scripts/migrate_timeout_history_once.py --guild-id 1234567890 --dry-run
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta

from utils.function import get_conn, ensure_timeout_table

TARGET_REASON = "거래 채널 구매,판매시 가격 미기재"
MANUAL_DISCORD_IDS = [
    391937781087207435,
    820544879012741161,
    495895015671857154,
    380718605421248514,
    654660814162362368,
    365163656742436864,
    626716005057429526,
    412503546261667870,
    863655781718163466,
    456115838311727105,
]


def parse_timeout_end(text: str | None) -> datetime | None:
    if not text:
        return None

    # 예: 타임아웃 해제 가능 시각: 2026년 03월 11일 18시 30분(KST)
    match = re.search(r"(\d{4})년\s*(\d{2})월\s*(\d{2})일\s*(\d{2})시\s*(\d{2})분", text)
    if not match:
        return None

    y, m, d, hh, mm = map(int, match.groups())
    return datetime(y, m, d, hh, mm)


def fetch_identity_by_nickname(cur, guild_id: int, nickname: str) -> tuple[int | None, str | None]:
    sql = f"""
        SELECT discord_user_id, stove_member_no FROM auth_accounts_{guild_id} WHERE nickname = %s
        UNION ALL
        SELECT discord_user_id, stove_member_no FROM deleted_auth_accounts_{guild_id} WHERE nickname = %s
        UNION ALL
        SELECT discord_user_id, stove_member_no FROM auth_sub_accounts_{guild_id} WHERE nickname = %s
        UNION ALL
        SELECT discord_user_id, stove_member_no FROM deleted_auth_sub_accounts_{guild_id} WHERE nickname = %s
        LIMIT 1
    """
    cur.execute(sql, (nickname, nickname, nickname, nickname))
    row = cur.fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def fetch_identity_nearby(cur, guild_id: int, blocked_by: int | None, created_at: datetime):
    cur.execute(
        """
        SELECT data_type, value
        FROM blocked_users
        WHERE guild_id = %s
          AND (%s IS NULL OR blocked_by = %s)
          AND created_at BETWEEN %s AND %s
          AND data_type IN ('discord_id', 'memberNo')
        ORDER BY created_at ASC
        """,
        (guild_id, blocked_by, blocked_by, created_at - timedelta(minutes=2), created_at + timedelta(minutes=2)),
    )
    rows = cur.fetchall()
    discord_id = None
    member_no = None
    for dtype, value in rows:
        if dtype == "discord_id" and str(value).isdigit() and discord_id is None:
            discord_id = int(value)
        if dtype == "memberNo" and member_no is None:
            member_no = value
    return discord_id, member_no


def upsert_timeout(cur, guild_id: int, discord_id: int, member_no: str | None, nickname: str | None,
                  start_at: datetime, end_at: datetime, created_by: int | None,
                  created_at: datetime, released_at: datetime | None):
    cur.execute(
        f"""
        INSERT INTO timeouts_{guild_id}
        (guild_id, discord_id, stove_member_no, nickname, reason, timeout_start_at, timeout_end_at, created_by, created_at, released_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            guild_id,
            discord_id,
            member_no,
            nickname,
            TARGET_REASON,
            start_at,
            end_at,
            created_by or 0,
            created_at,
            released_at,
        ),
    )


def migrate_from_blocked(cur, guild_id: int, dry_run: bool) -> list[int]:
    cur.execute(
        """
        SELECT id, value, reason, created_at, blocked_by, unblocked_at
        FROM blocked_users
        WHERE guild_id = %s
          AND data_type = 'nickname'
          AND reason LIKE %s
        ORDER BY created_at ASC
        """,
        (guild_id, "%타임아웃 해제 가능 시각:%"),
    )
    rows = cur.fetchall()

    touched_discord_ids: list[int] = []
    for row_id, nickname, reason, created_at, blocked_by, unblocked_at in rows:
        timeout_end = parse_timeout_end(reason)
        if not timeout_end:
            continue

        discord_id, member_no = fetch_identity_by_nickname(cur, guild_id, nickname)
        if not discord_id:
            fallback_did, fallback_member_no = fetch_identity_nearby(cur, guild_id, blocked_by, created_at)
            discord_id = discord_id or fallback_did
            member_no = member_no or fallback_member_no

        if not discord_id:
            print(f"[SKIP] row_id={row_id}, nickname={nickname} -> discord_id 찾기 실패")
            continue

        touched_discord_ids.append(discord_id)

        start_at = created_at
        released_at = unblocked_at

        if not dry_run:
            upsert_timeout(
                cur=cur,
                guild_id=guild_id,
                discord_id=discord_id,
                member_no=member_no,
                nickname=nickname,
                start_at=start_at,
                end_at=timeout_end,
                created_by=blocked_by,
                created_at=created_at,
                released_at=released_at,
            )

    return touched_discord_ids


def fetch_identity_by_discord(cur, guild_id: int, discord_id: int) -> tuple[str | None, str | None]:
    cur.execute(
        f"""
        SELECT stove_member_no, nickname FROM auth_accounts_{guild_id} WHERE discord_user_id = %s
        UNION ALL
        SELECT stove_member_no, nickname FROM deleted_auth_accounts_{guild_id} WHERE discord_user_id = %s
        UNION ALL
        SELECT stove_member_no, nickname FROM auth_sub_accounts_{guild_id} WHERE discord_user_id = %s
        UNION ALL
        SELECT stove_member_no, nickname FROM deleted_auth_sub_accounts_{guild_id} WHERE discord_user_id = %s
        LIMIT 1
        """,
        (discord_id, discord_id, discord_id, discord_id),
    )
    row = cur.fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def insert_manual_list(cur, guild_id: int, dry_run: bool) -> list[int]:
    start_at = datetime(2026, 3, 11, 0, 0, 0)
    end_at = datetime(2026, 3, 12, 0, 0, 0)
    released_at = end_at

    inserted: list[int] = []
    for discord_id in MANUAL_DISCORD_IDS:
        member_no, nickname = fetch_identity_by_discord(cur, guild_id, discord_id)

        if not dry_run:
            upsert_timeout(
                cur=cur,
                guild_id=guild_id,
                discord_id=discord_id,
                member_no=member_no,
                nickname=nickname,
                start_at=start_at,
                end_at=end_at,
                created_by=0,
                created_at=start_at,
                released_at=released_at,
            )
        inserted.append(discord_id)

    return inserted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--guild-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_conn() as conn, conn.cursor() as cur:
        ensure_timeout_table(cur, args.guild_id)

        migrated_ids = migrate_from_blocked(cur, args.guild_id, args.dry_run)
        manual_ids = insert_manual_list(cur, args.guild_id, args.dry_run)

        if args.dry_run:
            conn.rollback()
            print("[DRY-RUN] DB 반영 없이 종료")
        else:
            conn.commit()
            print("[DONE] timeout 이관 완료")

    print("\n[FROM_BLOCKED] discord_id 리스트")
    print(sorted(set(migrated_ids)))

    print("\n[MANUAL] discord_id 리스트")
    print(manual_ids)


if __name__ == "__main__":
    main()
