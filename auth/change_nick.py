import discord
from utils.function import get_main_account_nickname, update_main_account_nickname, get_setting_cached

class NickChangeView(discord.ui.View):
    OPTIONS_PER_SELECT = 25

    def __init__(self, guild_id: int, user_id: int, characters: list[dict]):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.user_id = user_id
        self.characters = characters
        self.selected_name: str | None = None

        # ✅ 현재 닉네임 가져오기 (DB 저장 닉네임)
        self.old_nick = get_main_account_nickname(guild_id, user_id)

        chunks = [
            self.characters[i : i + self.OPTIONS_PER_SELECT]
            for i in range(0, len(self.characters), self.OPTIONS_PER_SELECT)
        ]

        if not chunks:
            self.base_placeholders = []
            self.selects = []
            return

        self.base_placeholders = [
            self._build_placeholder(idx, len(chunks)) for idx in range(len(chunks))
        ]

        self.selects: list[NickChangeSelect] = []

        for idx, chunk in enumerate(chunks):
            select = NickChangeSelect(self, idx, chunk)
            self.selects.append(select)
            self.add_item(select)

        # ✅ 기본 embed (guild는 콜백에서 넣어줘야 함)
        self.embed: discord.Embed | None = None

    def build_embed(self, guild: discord.Guild | None) -> discord.Embed:
        """현재/선택 닉네임을 임베드로 구성"""
        embed = discord.Embed(
            title="✏️ 닉네임 변경",
            description="변경할 닉네임을 선택하고 확인 버튼을 눌러주세요.",
            color=0x3498db
        )

        display_old = self.add_sub_suffix(self.old_nick, guild)
        display_new = self.add_sub_suffix(self.selected_name, guild)

        embed.add_field(name="현재 닉네임", value=display_old or "없음", inline=True)
        embed.add_field(name="변경할 닉네임", value=display_new or "선택 안됨", inline=True)
        return embed

    def add_sub_suffix(self, nickname: str | None, guild: discord.Guild | None = None) -> str | None:
        """sub_auth_role 보유 시 닉네임 뒤에 ' | 부계정' 추가"""
        if not nickname:
            return nickname

        try:
            role_id = int(get_setting_cached(self.guild_id, "sub_auth_role") or 0)
            if not guild:
                return nickname
            member = guild.get_member(self.user_id)
            if member and any(r.id == role_id for r in member.roles):
                return f"{nickname} | 부계정O"
        except Exception:
            pass
        return nickname

    def _build_placeholder(self, index: int, total: int) -> str:
        if total <= 1:
            return "변경할 닉네임 선택"
        return f"닉네임 선택 {index + 1}"

    def apply_selection(self, index: int, nickname: str):
        self.selected_name = nickname
        for idx, select in enumerate(self.selects):
            for option in select.options:
                option.default = idx == index and option.value == nickname

            if idx == index:
                select.placeholder = f"{self.base_placeholders[idx]} · 선택: {nickname}"
            else:
                select.placeholder = self.base_placeholders[idx]

    async def handle_select(self, select: "NickChangeSelect", interaction: discord.Interaction):
        selected = select.values[0]
        self.apply_selection(select.index, selected)
        self.embed = self.build_embed(interaction.guild)
        await interaction.response.edit_message(embed=self.embed, view=self)

    @discord.ui.button(label="확인", style=discord.ButtonStyle.green, row=2)
    async def confirm(self, button: discord.ui.Button, interaction: discord.Interaction):
        from .auth_logger import send_nickname_change_log
        if not self.selected_name:
            await interaction.response.send_message("❌ 닉네임을 선택해주세요.", ephemeral=True)
            return

        if self.old_nick == self.selected_name:
            await interaction.response.send_message("⚠️ 기존 닉네임과 동일합니다.", ephemeral=True)
            return

        # ✅ DB 업데이트 (순수 닉네임만 저장)
        changed = update_main_account_nickname(self.guild_id, self.user_id, self.selected_name)
        if changed == 0:
            await interaction.response.send_message("❌ 닉네임 변경 실패 (대상 없음).", ephemeral=True)
            return

        # ✅ 디스코드 표시 닉네임 (sub_auth_role 있으면 접미사 추가)
        final_display_name = self.add_sub_suffix(self.selected_name, interaction.guild)

        try:
            await interaction.user.edit(nick=final_display_name)
        except Exception:
            pass

        embed = discord.Embed(title="✅ 닉네임 변경 완료", color=0x2ecc71)
        embed.add_field(name="이전 닉네임", value=self.add_sub_suffix(self.old_nick, interaction.guild) or "없음", inline=True)
        embed.add_field(name="새 닉네임", value=final_display_name, inline=True)
        await interaction.response.edit_message(embed=embed, view=None)
        
        # ✅ 로그 채널 전송
        await send_nickname_change_log(
            interaction.client,
            self.guild_id,
            interaction.user,
            self.old_nick,
            self.selected_name
        )

    @discord.ui.button(label="취소", style=discord.ButtonStyle.red, row=2)
    async def cancel(self, button: discord.ui.Button, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🚫 닉네임 변경 취소",
            description="닉네임 변경 요청이 취소되었습니다.",
            color=0xe74c3c
        )
        await interaction.response.edit_message(embed=embed, view=None)


class NickChangeSelect(discord.ui.Select):
    def __init__(self, parent_view: NickChangeView, index: int, characters: list[dict]):
        self.parent_view = parent_view
        self.index = index
        super().__init__(
            placeholder=parent_view.base_placeholders[index],
            options=[
                discord.SelectOption(
                    label=f"{c['CharacterName']} ({c['CharacterClassName']}, {c['ItemAvgLevel']})",
                    value=c["CharacterName"],
                )
                for c in characters
            ],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.parent_view.handle_select(self, interaction)
