from pathlib import Path

import discord
from . import auth_embed


from utils.function import (
    build_final_nickname,
    get_setting_cached,
    save_main_account,
    save_sub_account,
    fetch_character_list,
    is_main_registered,
    get_main_account_memberno,
    has_sub_accounts,
    delete_main_account,
)
from auth.auth_logger import send_main_delete_log

PROFILE_IMAGE_PATH = Path(__file__).resolve().parent.parent / "profile.png"

async def _reset_user_auth(interaction: discord.Interaction):
    """본계정 없이 부계정만 존재하는 사용자의 인증을 초기화"""
    main_nick, sub_list = delete_main_account(interaction.guild_id, interaction.user.id)
    member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None

    # 역할 제거
    for key in ("main_auth_role", "sub_auth_role"):
        role_id = get_setting_cached(interaction.guild_id, key)
        if role_id and member:
            role = interaction.guild.get_role(int(role_id))
            if role:
                try:
                    await member.remove_roles(role)
                except discord.Forbidden:
                    pass
    # 닉네임 초기화
    if member:
        try:
            await member.edit(nick=None)
        except discord.Forbidden:
            pass

    await send_main_delete_log(interaction.client, interaction.guild_id, interaction.user, main_nick, sub_list)


def _has_sub_only(guild_id: int, user_id: int) -> bool:
    return (not is_main_registered(guild_id, user_id)) and has_sub_accounts(guild_id, user_id)


class ResetAuthView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="🔄 인증 초기화", style=discord.ButtonStyle.danger, custom_id="auth_reset")
    async def reset(self, button: discord.ui.Button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await _reset_user_auth(interaction)
        await interaction.followup.send(
            "✅ 인증 정보를 초기화했습니다. 본계정 인증부터 다시 진행해주세요.",
            ephemeral=True,
        )
        self.stop()


async def send_reset_prompt_if_sub_only(interaction: discord.Interaction) -> bool:
    """부계정만 가진 상태라면 안내 메시지 + 초기화 버튼을 띄우고 True 반환"""
    if not _has_sub_only(interaction.guild_id, interaction.user.id):
        return False

    await interaction.response.send_message(
        "⚠️ 본계정 인증이 누락되어 있습니다.\n"
        "인증 현황을 초기화한 뒤, **본계정 인증**부터 다시 진행해주세요.",
        view=ResetAuthView(),
        ephemeral=True,
    )
    return True


class AuthMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="거래소 인증", style=discord.ButtonStyle.primary, custom_id="auth_trade")
    async def trade_auth(self, button: discord.ui.Button, interaction: discord.Interaction):
        # 거래소 인증 시작 안내 Embed + 진행 버튼 뷰
        if is_main_registered(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message("❌ 이미 인증된 계정입니다 인증 계정 설정 혹은 부계정 인증을 진행해주세요.", ephemeral=True)
            return
        embed = auth_embed.build_trade_intro_embed(get_setting_cached(interaction.guild_id,'main_auth_min_level'))
        view = AuthTradeIntroView(mode="main")
        if PROFILE_IMAGE_PATH.exists():
            await interaction.response.send_message(
                embed=embed,
                view=view,
                file=discord.File(PROFILE_IMAGE_PATH, filename="profile.png"),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="부계정 인증", style=discord.ButtonStyle.primary, custom_id="auth_sub")
    async def sub_auth(self, button: discord.ui.Button, interaction: discord.Interaction):
        if await send_reset_prompt_if_sub_only(interaction):
            return
        # ✅ 메인 계정 등록 여부 확인
        if not is_main_registered(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message(
                "❌ 먼저 본계정(거래소 인증)을 완료해야 부계정 인증이 가능합니다.",
                ephemeral=True
            )
            return

        # ✅ 본계정이 있으면 부계정 인증 안내 Embed + View 출력
        embed = auth_embed.build_sub_intro_embed()
        view = AuthTradeIntroView(mode="sub")
        if PROFILE_IMAGE_PATH.exists():
            await interaction.response.send_message(
                embed=embed, view=view, file=discord.File(PROFILE_IMAGE_PATH, filename="profile.png"), ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="닉네임 변경", style=discord.ButtonStyle.secondary, custom_id="auth_nick")
    async def nick_change(self, button: discord.ui.Button, interaction: discord.Interaction):
        from .change_nick import NickChangeView
        from utils.function import is_main_registered, get_main_account_memberno,fetch_character_list
        if await send_reset_prompt_if_sub_only(interaction):
            return
        # 본계정 등록 여부 확인
        if not is_main_registered(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message("❌ 먼저 본계정 인증을 완료해 주세요.", ephemeral=True)
            return

        # memberNo 조회
        member_no = get_main_account_memberno(interaction.guild_id, interaction.user.id)
        if not member_no:
            await interaction.response.send_message("⚠️ 본계정 정보를 찾을 수 없습니다.", ephemeral=True)
            return

        # 캐릭터 리스트 가져오기
        characters = await fetch_character_list(member_no, interaction.guild_id)
        if not characters:
            await interaction.response.send_message("⚠️ 캐릭터 정보를 불러오지 못했습니다.", ephemeral=True)
            return

        # 뷰 생성 + embed (guild 전달!)
        view = NickChangeView(interaction.guild_id, interaction.user.id, characters)
        await interaction.response.send_message(embed=view.build_embed(interaction.guild), view=view, ephemeral=True)


    @discord.ui.button(label="인증 계정 설정", style=discord.ButtonStyle.secondary, custom_id="auth_config")
    async def auth_config(self, button: discord.ui.Button, interaction: discord.Interaction):
        if await send_reset_prompt_if_sub_only(interaction):
            return
        if not is_main_registered(interaction.guild_id, interaction.user.id):
            await interaction.response.send_message("❌ 먼저 본계정 인증을 완료해 주세요.", ephemeral=True)
            return
        
        from .manage_view import AccountManageView
        view = AccountManageView(interaction.guild_id, interaction.user.id)
        embed = discord.Embed(
            title="⚙️ 인증 계정 관리",
            description="삭제할 계정을 선택하세요.",
            color=0x3498db
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class AuthTradeIntroView(discord.ui.View):
    def __init__(self, mode: str):
        super().__init__(timeout=600)
        self.mode = mode

    @discord.ui.button(label="진행하기", style=discord.ButtonStyle.success, custom_id="trade_start")
    async def start_trade_auth(self, button: discord.ui.Button, interaction: discord.Interaction):
        from . import auth_modal
        if self.mode == "main":
            await interaction.response.send_modal(auth_modal.AuthTradeModal())
        elif self.mode == "sub":
            await interaction.response.send_modal(auth_modal.AuthSubModal())
        
class RepChangeConfirmView(discord.ui.View):
    def __init__(self, auth_type: str, target_char: str, encrypt_member_no: str, main_char: str, characters: list[dict], memberno: int):
        super().__init__(timeout=600)
        self.auth_type = auth_type
        self.target_char = target_char
        self.encrypt_member_no = encrypt_member_no
        self.main_char = main_char
        self.characters = characters  # ✅ start_auth에서 가져온 데이터 그대로 저장
        self.member_no = memberno

    @discord.ui.button(label="변경 확인", style=discord.ButtonStyle.success, custom_id="rep_check")
    async def confirm_change(self, button: discord.ui.Button, interaction: discord.Interaction):
        from urllib.parse import unquote
        import aiohttp
        from .auth_flow import fetch_profile_url, verify_conditions, format_fail_message

        # 🔎 API는 대표캐릭터만 재검증
        async with aiohttp.ClientSession() as session:
            profile_url = await fetch_profile_url(session, self.encrypt_member_no)
            if not profile_url:
                await interaction.response.send_message("❌ 대표 캐릭터 확인 실패.", ephemeral=True)
                return
            current_main = unquote(profile_url.split("/")[-1])

        if current_main != self.target_char:
            await interaction.response.send_message(
                f"❌ 대표 캐릭터가 아직 **{self.target_char}** 로 변경되지 않았습니다.\n"
                f"(현재: {current_main})",
                ephemeral=True
            )
            return

        # ✅ 조건 검증 (characters는 start_auth에서 이미 받아둔 걸 사용)
        ok, result = await verify_conditions(
            self.auth_type,
            interaction.guild_id,
            interaction.user.id,
            self.member_no,
            self.characters
        )

        from ticket.ticket_create import create_ticket

        if not ok:
            reason, details = result
            if reason == "blocked":
                # ✅ 차단된 경우 → 재차 차단 등록 후 티켓 채널 생성
                from utils.function import block_user, get_user_blocked
                from block.block_commands import broadcast_block_log

                auto_reason = "차단 인증 시도(봇자동탐지)"
                nickname_list = [c["CharacterName"] for c in self.characters]
                original_details = details.get("details") if isinstance(details, dict) else details
                block_details = original_details
                bot_user_id = interaction.client.user.id if interaction.client.user else interaction.user.id
                member_no_value = str(self.member_no) if self.member_no else ""

                try:
                    extra_values = [("nickname", nick) for nick in nickname_list]
                    if member_no_value:
                        extra_values.append(("memberNo", member_no_value))

                    new_blocks, _ = block_user(
                        interaction.guild_id,
                        interaction.user.id,
                        auto_reason,
                        bot_user_id,
                        extra_values=extra_values,
                    )

                    refreshed = get_user_blocked(
                        interaction.guild_id,
                        interaction.user.id,
                        member_no_value,
                        nickname_list,
                    )

                    if new_blocks:
                        await broadcast_block_log(
                            interaction.client,
                            blocked_gid=interaction.guild_id,
                            target_user=interaction.guild.get_member(interaction.user.id),
                            raw_user_id=interaction.user.id,
                            new_blocks=new_blocks,
                            reason=auto_reason,
                            blocked_by=bot_user_id,
                        )

                    block_details = refreshed or original_details

                except Exception:
                    msg = format_fail_message(reason, details)
                    await interaction.response.send_message(msg, ephemeral=True)
                    return

                await create_ticket(interaction.user, "차단", block_data=block_details)

                embed = discord.Embed(
                    title="🚫 차단된 사용자",
                    description="차단된 사용자로 확인되어 전용 문의 채널이 열렸습니다.\n\n"
                                "📌 생성된 채널에서 관리자와 소통하여 이의 제기를 진행해 주세요.",
                    color=discord.Color.red()
                )

                await interaction.response.edit_message(
                    content=None,
                    embed=embed,
                    view=None, delete_after=10
                )
                return

            else:
                # ✅ 차단 외 다른 사유 → 기존 방식
                msg = format_fail_message(reason, details)
                await interaction.response.send_message(msg, ephemeral=True)
                return

        
        # ✅ 다음 단계 → 닉네임 선택 뷰 띄우기 (캐릭터가 없는 경우 예외 처리)
        if not self.characters:
            await interaction.response.edit_message(
                content="❌ 선택할 수 있는 캐릭터를 찾지 못했습니다. 다시 인증을 진행해 주세요.",
                embed=None,
                view=None
            )
            return

        await interaction.response.edit_message(
            content="서버에 사용할 대표 캐릭터를 선택해주세요:",
            embed=None,
            view=NicknameSelectView(self.auth_type, self.member_no, self.characters)
        )
            
class NicknameSelectView(discord.ui.View):
    OPTIONS_PER_SELECT = 25

    def __init__(self, auth_type: str, member_no: str, characters: list[dict]):
        super().__init__(timeout=600)
        self.auth_type = auth_type
        self.member_no = member_no
        self.characters = characters
        self.selected_nick: str | None = None
        self.selects: list[NicknameSelect] = []

        chunks = [
            self.characters[i : i + self.OPTIONS_PER_SELECT]
            for i in range(0, len(self.characters), self.OPTIONS_PER_SELECT)
        ]

        if not chunks:
            self.base_placeholders = []
            return

        self.base_placeholders = [
            self._build_placeholder(idx, len(chunks)) for idx in range(len(chunks))
        ]

        for idx, chunk in enumerate(chunks):
            select = NicknameSelect(self, idx, chunk)
            self.selects.append(select)
            self.add_item(select)

    def _build_placeholder(self, index: int, total: int) -> str:
        if total <= 1:
            return "사용할 닉네임을 선택하세요"
        return f"사용할 닉네임 목록 {index + 1}"

    def apply_selection(self, index: int, nickname: str):
        self.selected_nick = nickname
        for idx, select in enumerate(self.selects):
            for option in select.options:
                option.default = idx == index and option.value == nickname

            if idx == index:
                select.placeholder = f"{self.base_placeholders[idx]} · 선택: {nickname}"
            else:
                select.placeholder = self.base_placeholders[idx]

    @discord.ui.button(label="✅ 확인", style=discord.ButtonStyle.success, custom_id="nick_confirm", row=2)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        if not self.selected_nick:
            await interaction.response.send_message("⚠️ 닉네임을 먼저 선택해주세요.", ephemeral=True)
            return

        # ✅ 선택한 캐릭터 정보 찾기
        char_info = next((c for c in self.characters if c["CharacterName"] == self.selected_nick), None)

        member = interaction.guild.get_member(interaction.user.id)

        if self.auth_type == "main":
            save_main_account(
                interaction.guild_id,
                interaction.user.id,
                self.member_no,
                self.selected_nick
            )
            if member:
                new_name = build_final_nickname(
                    interaction.guild_id,
                    interaction.user.id,
                    self.selected_nick,
                    is_main=True
                )
                try:
                    await member.edit(nick=new_name)
                except discord.Forbidden:
                    pass

            # ✅ 인증 로그 (본계정)
            if char_info:
                from .auth_logger import send_trade_auth_log
                await send_trade_auth_log(
                    interaction.client,
                    interaction.guild_id,
                    interaction.user,
                    char_info["CharacterName"],
                    char_info["ServerName"],
                    char_info["ItemAvgLevel"]
                )

        else:  # sub 계정
            sub_number = save_sub_account(
                interaction.guild_id,
                interaction.user.id,
                self.member_no,
                self.selected_nick
            )
            if member:
                new_name = build_final_nickname(
                    interaction.guild_id,
                    interaction.user.id,
                    interaction.user.nick or interaction.user.global_name,
                    is_main=False
                )
                try:
                    await member.edit(nick=new_name)
                except discord.Forbidden:
                    pass

            # ✅ 인증 로그 (부계정)
            if char_info:
                from auth.auth_logger import send_sub_auth_log
                await send_sub_auth_log(
                    interaction.client,
                    interaction.guild_id,
                    interaction.user,
                    sub_number=sub_number,
                    character_name=char_info["CharacterName"],
                    server_name=char_info["ServerName"],
                    item_level=char_info["ItemAvgLevel"]
                )

        # ✅ 역할 부여
        role_key = "sub_auth_role" if self.auth_type == "sub" else "main_auth_role"
        role_id = get_setting_cached(interaction.guild_id, role_key)
        if role_id and member:
            role = interaction.guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    pass

        await interaction.response.edit_message(
            content=f"✅ 닉네임 `{self.selected_nick}` 로 인증이 완료되었습니다!",
            view=None,
            delete_after=30
        )
        self.stop()

    @discord.ui.button(label="❌ 취소", style=discord.ButtonStyle.danger, custom_id="nick_cancel",row=2)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        # ✅ 기존 메시지 수정 + 30초 뒤 삭제
        await interaction.response.edit_message(
            content="🚫 인증이 취소되었습니다.",
            view=None,delete_after=30
        )
        self.stop()

class NicknameSelect(discord.ui.Select):
    def __init__(self, parent_view: NicknameSelectView, index: int, characters: list[dict]):
        self.parent_view = parent_view
        self.index = index
        placeholder = parent_view.base_placeholders[index]
        super().__init__(
            placeholder=placeholder,
            options=[
                discord.SelectOption(
                    label=c["CharacterName"],
                    description=f"{c['ServerName']} | Lv.{c['ItemAvgLevel']}",
                    value=c["CharacterName"],
                )
                for c in characters
            ],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        self.parent_view.apply_selection(self.index, selected)
        await interaction.response.edit_message(view=self.parent_view)
