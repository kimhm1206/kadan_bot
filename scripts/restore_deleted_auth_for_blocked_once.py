"""특정 discord_id 목록에 대해 삭제 인증 테이블 -> 인증 테이블 복구를 수행하는 1회용 스크립트.

규칙
- 현재 차단(unblocked_at IS NULL) 상태인 유저만 복구
- 이미 복구되어 인증 테이블에 존재하는 경우 스킵
- 복구한 discord_id 목록을 출력
"""

from __future__ import annotations

import argparse

from utils.function import get_conn

TARGET_DISCORD_IDS = [
    159522611972276224,
    256425208800477184,
    315108136669413379,
    331100990625284097,
    345235195747762178,
    364014371497836544,
    369410059345723416,
    576441660045524993,
    794908049730174976,
    1023261980284440637,
    1265358451828199456,
]


def _get_identity_values(cur, guild_id: int, discord_id: int) -> tuple[set[str], set[str]]:
    cur.execute(
        f"""
        SELECT stove_member_no, nickname FROM auth_accounts_{guild_id} WHERE discord_user_id = %s
        UNION ALL
        SELECT stove_member_no, nickname FROM deleted_auth_accounts_{guild_id} WHERE discord_user_id = %s
        UNION ALL
        SELECT stove_member_no, nickname FROM auth_sub_accounts_{guild_id} WHERE discord_user_id = %s
        UNION ALL
        SELECT stove_member_no, nickname FROM deleted_auth_sub_accounts_{guild_id} WHERE discord_user_id = %s
        """,
        (discord_id, discord_id, discord_id, discord_id),
    )
    member_nos: set[str] = set()
    nicknames: set[str] = set()
    for member_no, nickname in cur.fetchall():
        if member_no:
            member_nos.add(str(member_no))
        if nickname:
            nicknames.add(str(nickname))
    return member_nos, nicknames


def is_still_blocked(cur, guild_id: int, discord_id: int) -> bool:
    member_nos, nicknames = _get_identity_values(cur, guild_id, discord_id)

    conditions = ["(data_type = 'discord_id' AND value = %s)"]
    params: list[str | int] = [str(discord_id)]

    if member_nos:
        placeholders = ", ".join(["%s"] * len(member_nos))
        conditions.append(f"(data_type = 'memberNo' AND value IN ({placeholders}))")
        params.extend(member_nos)

    if nicknames:
        placeholders = ", ".join(["%s"] * len(nicknames))
        conditions.append(f"(data_type = 'nickname' AND value IN ({placeholders}))")
        params.extend(nicknames)

    where_cond = " OR ".join(conditions)
    cur.execute(
        f"""
        SELECT 1
        FROM blocked_users
        WHERE guild_id = %s
          AND unblocked_at IS NULL
          AND ({where_cond})
        LIMIT 1
        """,
        (guild_id, *params),
    )
    return cur.fetchone() is not None


def restore_main(cur, guild_id: int, discord_id: int, dry_run: bool) -> bool:
    cur.execute(
        f"SELECT 1 FROM auth_accounts_{guild_id} WHERE discord_user_id = %s LIMIT 1",
        (discord_id,),
    )
    if cur.fetchone():
        return False

    cur.execute(
        f"""
        SELECT id, discord_user_id, stove_member_no, nickname, is_verified, created_at, verified_at
        FROM deleted_auth_accounts_{guild_id}
        WHERE discord_user_id = %s
        ORDER BY deleted_at DESC NULLS LAST, id DESC
        LIMIT 1
        """,
        (discord_id,),
    )
    row = cur.fetchone()
    if not row:
        return False

    del_id, did, member_no, nickname, is_verified, created_at, verified_at = row

    if not dry_run:
        cur.execute(
            f"""
            INSERT INTO auth_accounts_{guild_id}
            (discord_user_id, stove_member_no, nickname, is_verified, created_at, verified_at, expired_at)
            VALUES (%s, %s, %s, %s, %s, %s, NULL)
            """,
            (did, member_no, nickname, is_verified, created_at, verified_at),
        )
        cur.execute(
            f"DELETE FROM deleted_auth_accounts_{guild_id} WHERE id = %s AND discord_user_id = %s",
            (del_id, discord_id),
        )

    return True


def restore_subs(cur, guild_id: int, discord_id: int, dry_run: bool) -> bool:
    cur.execute(
        f"""
        SELECT id, sub_number, stove_member_no, nickname, created_at
        FROM deleted_auth_sub_accounts_{guild_id}
        WHERE discord_user_id = %s
        ORDER BY id ASC
        """,
        (discord_id,),
    )
    rows = cur.fetchall()
    if not rows:
        return False

    moved_any = False

    for del_id, sub_number, member_no, nickname, created_at in rows:
        cur.execute(
            f"""
            SELECT 1
            FROM auth_sub_accounts_{guild_id}
            WHERE discord_user_id = %s
              AND (
                (stove_member_no IS NOT NULL AND stove_member_no = %s)
                OR (nickname IS NOT NULL AND nickname = %s)
              )
            LIMIT 1
            """,
            (discord_id, member_no, nickname),
        )
        if cur.fetchone():
            # 이미 복구/존재하는 서브는 삭제 테이블에서만 정리
            if not dry_run:
                cur.execute(
                    f"DELETE FROM deleted_auth_sub_accounts_{guild_id} WHERE id = %s",
                    (del_id,),
                )
            continue

        cur.execute(
            f"""
            SELECT 1
            FROM auth_sub_accounts_{guild_id}
            WHERE discord_user_id = %s AND sub_number = %s
            LIMIT 1
            """,
            (discord_id, sub_number),
        )
        conflict = cur.fetchone() is not None

        new_sub_number = sub_number
        if conflict:
            cur.execute(
                f"SELECT COALESCE(MAX(sub_number), 0) FROM auth_sub_accounts_{guild_id} WHERE discord_user_id = %s",
                (discord_id,),
            )
            max_num = cur.fetchone()[0] or 0
            new_sub_number = max_num + 1

        if not dry_run:
            cur.execute(
                f"""
                INSERT INTO auth_sub_accounts_{guild_id}
                (discord_user_id, sub_number, stove_member_no, nickname, created_at, deleted_at)
                VALUES (%s, %s, %s, %s, %s, NULL)
                """,
                (discord_id, new_sub_number, member_no, nickname, created_at),
            )
            cur.execute(
                f"DELETE FROM deleted_auth_sub_accounts_{guild_id} WHERE id = %s",
                (del_id,),
            )
        moved_any = True

    return moved_any


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--guild-id", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    restored_ids: list[int] = []
    skipped_unblocked: list[int] = []
    skipped_no_source: list[int] = []

    with get_conn() as conn, conn.cursor() as cur:
        for discord_id in TARGET_DISCORD_IDS:
            if not is_still_blocked(cur, args.guild_id, discord_id):
                # 차단 해제된 유저는 작업하지 않음
                skipped_unblocked.append(discord_id)
                continue

            main_restored = restore_main(cur, args.guild_id, discord_id, args.dry_run)
            sub_restored = restore_subs(cur, args.guild_id, discord_id, args.dry_run)

            if main_restored or sub_restored:
                restored_ids.append(discord_id)
            else:
                skipped_no_source.append(discord_id)

        if args.dry_run:
            conn.rollback()
            print("[DRY-RUN] DB 반영 없이 종료")
        else:
            conn.commit()
            print("[DONE] 복구 작업 완료")

    print("\n[RESTORED_DISCORD_IDS]")
    print(restored_ids)
    print(f"count={len(restored_ids)}")

    print("\n[SKIPPED_UNBLOCKED_IDS]")
    print(skipped_unblocked)
    print(f"count={len(skipped_unblocked)}")

    print("\n[SKIPPED_NO_SOURCE_OR_ALREADY_RESTORED_IDS]")
    print(skipped_no_source)
    print(f"count={len(skipped_no_source)}")


if __name__ == "__main__":
    main()
