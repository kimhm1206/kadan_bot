
# 앞으로 붙을 모듈 import 자리
# from .auth_profile import get_encrypt_member_no, fetch_profile
# from .auth_validators import check_duplicate, check_level, check_blocked
# from .auth_saver import save_main_account, save_sub_account
# from . import auth_embed

import discord
import aiohttp
import os
from urllib.parse import unquote
from utils.function import get_setting_cached  # ✅ 서버 설정 캐시에서 불러오기
from .auth_embed import build_rep_change_embed
from utils.function import is_account_duplicate, get_user_blocked,is_memberno_duplicate

API_TOKEN = os.getenv("API_TOKEN")  # .env에 저장된 토큰

async def start_auth(auth_type: str, interaction: discord.Interaction, member_no: str):
    """
    인증 메인 흐름 컨트롤러
    :param auth_type: "main" (본계정) / "sub" (부계정)
    :param interaction: Discord Interaction 객체
    :param member_no: 프로필 링크에서 추출한 숫자 memberNo
    """
    guild_id = interaction.guild_id
    discord_id = interaction.user.id
    server = get_setting_cached(guild_id, "server")
    
    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession() as session:
        # 1️⃣ encryptMemberNo 변환
        encrypt_member_no = await get_encrypt_member_no(session, member_no)
        if not encrypt_member_no:
            await interaction.followup.send("❌ STOVE API 응답 실패.", ephemeral=True)
            return

        # 2️⃣ 전투정보실 URL (리다이렉트 최종 URL 확보)
        profile_url = await fetch_profile_url(session, encrypt_member_no)
        if not profile_url:
            await interaction.followup.send("❌ 전투정보실 URL 가져오기 실패.", ephemeral=True)
            return

        # 대표 캐릭터 (URL에서 추출 후 디코딩)
        main_char_encoded = profile_url.split("/")[-1]
        main_char = unquote(main_char_encoded)

        # 3️⃣ Lost Ark API로 전체 캐릭터 조회
        characters = await fetch_characters_from_api(session, main_char)
        if not characters:
            await interaction.followup.send("❌ 캐릭터 목록을 불러오지 못했습니다.", ephemeral=True)
            return

    # 4️⃣ 서버 필터링
    
    filtered_chars = [c for c in characters if c["ServerName"] == server]

    if not filtered_chars:
        await interaction.followup.send(
            f"❌ 이 계정에는 **{server} 서버 캐릭터**가 없습니다.", ephemeral=True
        )
        return
    
    if not filtered_chars or len(filtered_chars) < 2:
        await interaction.followup.send(
            f"❌ 이 계정에는 **{server} 서버 캐릭터**가 2개 이상 있어야 인증이 가능합니다.",
            ephemeral=True
        )
        return
    
    from .auth_view import RepChangeConfirmView
    
    # 5️⃣ 대표 캐릭터 변경 요청 Embed + View
    embed, target_char = build_rep_change_embed(main_char, server, filtered_chars)

    # characters도 같이 넘겨줌
    view = RepChangeConfirmView(auth_type, target_char, encrypt_member_no, main_char, filtered_chars, member_no)

    await interaction.edit_original_response(embed=embed, view=view)

        
        
async def get_encrypt_member_no(session: aiohttp.ClientSession, member_no: str) -> str | None:
    """
    STOVE API를 통해 encryptMemberNo를 가져오는 함수
    :param session: aiohttp.ClientSession
    :param member_no: 숫자 memberNo (예: "84599446")
    :return: encryptMemberNo (문자열) 또는 None
    """
    url = "https://lostark.game.onstove.com/board/IsCharacterList"
    payload = {"memberNo": member_no}
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        async with session.post(url, data=payload, headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            return data.get("encryptMemberNo")
    except Exception:
        return None

from urllib.parse import quote

async def fetch_profile_url(session: aiohttp.ClientSession, encrypt_member_no: str) -> str | None:
    """
    전투정보실 링크에 접속해서 최종 리다이렉트된 URL만 반환
    :param session: aiohttp.ClientSession
    :param encrypt_member_no: STOVE API에서 얻은 encryptMemberNo
    :return: 최종 URL (str) 또는 None
    """
    url = f"https://lostark.game.onstove.com/Profile/Member?id={quote(encrypt_member_no)}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        async with session.get(url, headers=headers, allow_redirects=True) as resp:
            if resp.status != 200:
                return None
            final_url = str(resp.url)  # ✅ 리다이렉트 후 최종 주소
            return final_url
    except Exception:
        return None

async def fetch_characters_from_api(session: aiohttp.ClientSession, character_name: str) -> list[dict] | None:
    """
    Lost Ark API로 캐릭터 전체 목록 조회
    :param session: aiohttp.ClientSession
    :param character_name: 대표 캐릭터 닉네임
    :return: 캐릭터 리스트 (닉네임/서버/레벨 포함) or None
    """
    url = f"https://developer-lostark.game.onstove.com/characters/{character_name}/siblings"
    headers = {
        "Authorization": f"bearer {API_TOKEN}",
        "User-Agent": "Mozilla/5.0"
    }

    try:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            # data 예시: [{ "CharacterName": "닉네임", "ServerName": "서버", "ItemMaxLevel": "1675.00", ... }]
            return data
    except Exception:
        return None
    

async def verify_conditions(auth_type, guild_id, discord_id, member_no, characters):
    nickname_list = [c["CharacterName"] for c in characters]

    # 1️⃣ 중복 검사
    if auth_type == "main":
        # 본계정 + 부계정 모두 검사 (discord_id, memberNo, nickname 전부)
        duplicates = is_account_duplicate(guild_id, discord_id, member_no, nickname_list)
        if duplicates:
            return False, ("duplicate", duplicates)

    elif auth_type == "sub":
        # 본계정 + 부계정 테이블 전부에서 memberNo만 검사
        duplicates = is_memberno_duplicate(guild_id, member_no)
        if duplicates:
            return False, ("duplicate_sub", duplicates)

    # 2️⃣ 레벨 조건
    if auth_type == "main":
        min_ilvl = float(get_setting_cached(guild_id, "main_auth_min_level"))
        
        ilvls = []
        for c in characters:
            try:
                ilvls.append(float(c["ItemAvgLevel"].replace(",", "")))
            except:
                continue
        if not ilvls or max(ilvls) < min_ilvl:
            return False, ("ilevel", min_ilvl)

    # 3️⃣ 차단 검사 (공통)
    blocked = get_user_blocked(guild_id, discord_id, member_no, nickname_list)
    if blocked:
        return False, (
            "blocked",
            {
                "details": blocked,
                "discord_id": discord_id,
                "member_no": member_no,
                "nicknames": nickname_list,
            },
        )

    return True, ("ok", "검증 통과")

def format_fail_message(reason: str, details) -> str:
    if reason == "duplicate":
        dup_list = [f"{d[0]} ({d[1]})" for d in details]
        return "❌ 이미 등록된 계정이 있습니다.\n- " + "\n- ".join(dup_list)

    elif reason == "duplicate_sub":
        dup_list = [f"{d[0]} ({d[1]})" for d in details]
        return "❌ 이미 등록된 부계정입니다.\n- " + "\n- ".join(dup_list)

    elif reason == "ilevel":
        return f"⚠️ 아이템 레벨 조건을 충족하지 못했습니다.\n최소 요구 레벨: {details}"

    elif reason == "blocked":
        blocked_details = details.get("details") if isinstance(details, dict) else details
        blocked_details = blocked_details or []
        reason_list = [
            f"[서버:{b['guild_id']}] {b['data_type']}={b['value']} (사유:{b['reason']})"
            for b in blocked_details
        ]
        return "🚫 차단된 사용자입니다.\n" + "\n".join(reason_list) + "\n관리자에게 문의해주세요."

    else:
        return "❌ 인증에 실패했습니다. 다시 시도해주세요."
