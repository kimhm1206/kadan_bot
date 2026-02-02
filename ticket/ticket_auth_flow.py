import asyncio
from typing import Awaitable, Callable, Optional

import discord

from utils.function import get_conn


async def start_auth_ticket_flow(
    *,
    channel: discord.TextChannel,
    member: discord.Member,
    guild: discord.Guild,
    guild_id: int,
    ticket_type: str,
    icon: str,
    log_channel: Optional[discord.TextChannel],
    archive_ticket_channel_fn: Callable[..., Awaitable[None]],
    close_ticket_message: Callable[[discord.Message, bool], Awaitable[None]],
    close_ticket: Callable[[discord.Interaction, bool], Awaitable[None]],
    ticket_control_view_factory: Callable[[], discord.ui.View],
) -> None:
    """인증/문의 흐름이 필요한 티켓의 상호작용을 분리 관리합니다."""
    await channel.set_permissions(member, send_messages=False)

    # ✅ 챗봇 시작 안내
    chatbot_embed = discord.Embed(
        title=f"{icon} {ticket_type} 시작 안내",
        description=f"**{member.mention} 님, 안내에 따라 진행해 주세요.**",
        color=discord.Color.blurple(),
    )
    chatbot_embed.add_field(
        name="🧭 진행 방법",
        value=(
            "아래 버튼을 눌러 문의 유형을 선택해 주세요.\n"
            "선택 후에 필요한 안내를 바로 제공해드립니다."
        ),
        inline=False,
    )
    chatbot_embed.add_field(
        name="⏱️ 유의사항",
        value="5분 동안 아무 작업이 없으면 자동 종료됩니다.",
        inline=False,
    )

    # ✅ 인증이 아닌 일반 문의 안내
    inquiry_embed = discord.Embed(
        title=f"{icon} 문의 접수 안내",
        description=(
            f"**{member.mention} 님, 아래에 문의 내용을 작성해 주세요.**"
        ),
        color=discord.Color.blue(),
    )
    inquiry_embed.add_field(
        name="💬 안내",
        value=(
            "서로 존중하는 태도로 예쁘게 이야기해 주세요. 🙏\n"
            "문의가 끝나면 **문의 종료** 버튼으로 티켓을 종료할 수 있습니다."
        ),
        inline=False,
    )

    # ✅ 인증 안내 시작 임베드
    auth_embed = discord.Embed(
        title="🔑 인증 관련 도움 센터",
        description="원하시는 항목을 선택해 주세요.",
        color=discord.Color.purple(),
    )
    auth_embed.add_field(
        name="📌 FAQ · 많이 묻는 질문",
        value=(
            "1️⃣ 마이페이지 프로필 주소가 올바르지 않다고 떠요.\n"
            "2️⃣ 대표캐릭터를 어디서 바꿔야하는지 모르겠어요.\n"
            "3️⃣ 대표캐릭터는 다른걸로하고싶은데 안바꾸는 방법은 없나요?\n"
            "4️⃣ 봇이 대표로 바꾸라는 캐릭터는 1660 이하인캐릭터인데 문제 없나요?\n"
            "5️⃣ 계정을 구매 및 양도 받았는데 중복인증이라고 인증이 안되고 있어요.\n"
            "6️⃣ 제계졍을 인증하는데 중복인증이라고 나와요."
        ),
        inline=False,
    )
    auth_embed.add_field(
        name="⏱️ 자동 종료 안내",
        value="5분 동안 아무 작업이 없을 경우 자동 종료됩니다.",
        inline=False,
    )
    auth_embed.set_footer(text="필요 시 관리자에게 문의하기 버튼으로 이동하세요.")

    # ✅ 인증 영상 안내 텍스트
    auth_tip_text = (
        "1) 아래 영상을 보고 제시도 해주세요.\n"
        "2) 제시도 후에도 안될 시 **봇이 응답하는 화면을 캡쳐**해 주세요.\n"
        "3) **관리자에게 문의하기** 버튼을 눌러 캡쳐본을 전송해주세요.\n\n"
        "📎 **캡쳐본이 없으면 관리자가 확인 후 문의를 종료합니다.**"
    )

    def lookup_auth_records(member_no: str) -> tuple[str, list[int]]:
        current_rows: list[tuple[int, str | None]] = []
        table_map = [
            (f"auth_accounts_{guild_id}", current_rows),
        ]
        with get_conn() as conn, conn.cursor() as cur:
            for table, target in table_map:
                cur.execute(
                    f"SELECT discord_user_id, nickname FROM {table} WHERE stove_member_no = %s",
                    (member_no,),
                )
                target.extend(cur.fetchall())

        if not current_rows:
            return "❌ 해당 번호로 인증 기록을 찾지 못했습니다.", []

        def build_lines(rows: list[tuple[int, str | None]], suffix: str = "") -> tuple[list[str], list[int]]:
            nickname_map: dict[int, str] = {}
            discord_ids: list[int] = []
            for discord_id, nickname in rows:
                if not discord_id:
                    continue
                discord_id = int(discord_id)
                if discord_id not in nickname_map:
                    nickname_map[discord_id] = nickname or "닉네임 없음"
                    discord_ids.append(discord_id)

            lines: list[str] = []
            for discord_id in discord_ids:
                mention = f"<@{discord_id}>"
                nickname = nickname_map.get(discord_id, "닉네임 없음")
                line = f"- {mention} (discord_id={discord_id}, nickname={nickname})"
                if suffix:
                    line = f"{line} {suffix}"
                lines.append(line)
            return lines, discord_ids

        current_lines, current_ids = build_lines(current_rows)

        result_text = "\n".join(
            [
                "현재 인증중 계정 -",
                "\n".join(current_lines) if current_lines else "없음",
            ]
        )
        return result_text, current_ids

    async def auto_close_and_delete():
        await archive_ticket_channel_fn(
            channel=channel,
            deleter=guild.me,
            log_channel=log_channel,
            ticket_type=ticket_type,
            owner_label=member.mention,
        )

    timeout_task: asyncio.Task | None = None

    async def schedule_timeout(action: str):
        nonlocal timeout_task
        if timeout_task and not timeout_task.done():
            timeout_task.cancel()

        async def _timeout():
            try:
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                return

            if action == "delete":
                await auto_close_and_delete()
            elif action == "close":
                await close_ticket_message(chatbot_message, allow_delete=True)

        timeout_task = asyncio.create_task(_timeout())

    class TicketChatbotView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="인증 관련", style=discord.ButtonStyle.primary, emoji="🔑")
        async def auth_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="인증이 아닌 다른 문의", style=discord.ButtonStyle.success, emoji="💬")
        async def other_inquiry_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != member.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 요청자만 사용할 수 있습니다.", ephemeral=True)
                return

            if timeout_task and not timeout_task.done():
                timeout_task.cancel()

            await channel.set_permissions(member, send_messages=True, attach_files=True, embed_links=True)
            await interaction.response.edit_message(embed=inquiry_embed, view=ticket_control_view_factory())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        async def _reset_timeout(self):
            await schedule_timeout("close")

        async def _send_video_response(self, interaction: discord.Interaction, url: str, video_label: str):
            await self._reset_timeout()
            question_label = (
                "1️⃣ 마이페이지 프로필 주소가 올바르지 않다고 떠요."
                if url.startswith("https://cdn.discordapp.com/attachments/1467748338328670229/1467748552758263901/")
                else "2️⃣ 대표캐릭터를 어디서 바꿔야하는지 모르겠어요."
            )
            video_embed = discord.Embed(
                title="📹 인증 도움 영상",
                color=discord.Color.blurple(),
            )
            video_embed.add_field(name="🧾 질문", value=question_label, inline=False)
            video_embed.add_field(name="✅ 답변", value=auth_tip_text, inline=False)
            video_embed.add_field(
                name="🔗 영상 확인",
                value="아래 메시지에서 영상을 확인해 주세요.",
                inline=False,
            )
            video_embed.set_footer(text="필요 시 관리자에게 문의를 이어주세요.")
            await interaction.response.edit_message(embed=video_embed, view=TicketAuthResponseView(url))
            await interaction.followup.send(f"{video_label}\n{url}")

        @discord.ui.button(label="1번", style=discord.ButtonStyle.primary, row=0)
        async def option_one(self, button: discord.ui.Button, interaction: discord.Interaction):
            await self._send_video_response(
                interaction,
                "https://cdn.discordapp.com/attachments/1467748338328670229/1467748552758263901/b6979124805680fd.mp4?ex=698182dc&is=6980315c&hm=a7072ddf9bc547553a090d5b56512cf234e56e8ff17007bbd06e6346f89b9c32&",
                "마이페이지 링크 영상",
            )

        @discord.ui.button(label="2번", style=discord.ButtonStyle.primary, row=0)
        async def option_two(self, button: discord.ui.Button, interaction: discord.Interaction):
            await self._send_video_response(
                interaction,
                "https://cdn.discordapp.com/attachments/1467748338328670229/1467748551147651102/15e7b960aa938d11.mp4?ex=698182dc&is=6980315c&hm=90d5e6048058f161dcee7e6948f9cca38d6053b85c994260dac0f009ba7ddc66&",
                "대표 캐릭터 변경 영상",
            )

        @discord.ui.button(label="3번", style=discord.ButtonStyle.primary, row=0)
        async def option_three(self, button: discord.ui.Button, interaction: discord.Interaction):
            await self._reset_timeout()
            text_embed = discord.Embed(title="✅ 인증 안내", color=discord.Color.blurple())
            text_embed.add_field(
                name="🧾 질문",
                value="3️⃣ 대표캐릭터는 다른걸로하고싶은데 안바꾸는 방법은 없나요?",
                inline=False,
            )
            text_embed.add_field(
                name="✅ 답변",
                value=(
                    "인증 과정에서 바꾸는 대표캐릭터는 계정 소유 확인용으로만 이용됩니다. "
                    "인증 완료 후 아무캐릭터로나 바꾸셔도 상관없습니다.\n"
                    "또한 인증 완료 후 디스코드에서 사용할 대표캐릭터를 선택하는 화면이 나오니 "
                    "인증 절차에 따라주시면 됩니다."
                ),
                inline=False,
            )
            await interaction.response.edit_message(embed=text_embed, view=TicketAuthTextView())

        @discord.ui.button(label="4번", style=discord.ButtonStyle.primary, row=1)
        async def option_four(self, button: discord.ui.Button, interaction: discord.Interaction):
            await self._reset_timeout()
            text_embed = discord.Embed(title="✅ 인증 안내", color=discord.Color.blurple())
            text_embed.add_field(
                name="🧾 질문",
                value="4️⃣ 봇이 대표로 바꾸라는 캐릭터는 1660 이하인캐릭터인데 문제 없나요?",
                inline=False,
            )
            text_embed.add_field(
                name="✅ 답변",
                value=(
                    "인증 과정에서 바꾸는 대표캐릭터는 계정 소유 확인용으로만 이용됩니다. "
                    "원정대 내 지정된 레벨 이상의 캐릭터가 하나라도 존재하면, 문제 없이 인증 가능합니다.\n"
                    "또한 인증 완료 후 디스코드에서 사용할 대표캐릭터를 선택하는 화면이 나오니 "
                    "인증 절차에 따라주시면 됩니다."
                ),
                inline=False,
            )
            await interaction.response.edit_message(embed=text_embed, view=TicketAuthTextView())

        @discord.ui.button(label="5번", style=discord.ButtonStyle.primary, row=1)
        async def option_five(self, button: discord.ui.Button, interaction: discord.Interaction):
            await self._reset_timeout()
            embed = discord.Embed(title="🧾 인증 안내", color=discord.Color.blurple())
            embed.add_field(
                name="🧾 질문",
                value="5️⃣ 계정을 구매 및 양도 받았는데 중복인증이라고 인증이 안되고 있어요.",
                inline=False,
            )
            embed.add_field(
                name="✅ 답변",
                value=(
                    "우선 기존 인증을 조회합니다.\n"
                    "아래 버튼을 눌러 인증 시 사용되는 마이페이지 링크를 입력해주세요."
                ),
                inline=False,
            )
            await interaction.response.edit_message(embed=embed, view=TicketAuthTransferView())

        @discord.ui.button(label="6번", style=discord.ButtonStyle.primary, row=1)
        async def option_six(self, button: discord.ui.Button, interaction: discord.Interaction):
            await self._reset_timeout()
            embed = discord.Embed(title="🧾 인증 안내", color=discord.Color.blurple())
            embed.add_field(
                name="🧾 질문",
                value="6️⃣ 제계졍을 인증하는데 중복인증이라고 나와요.",
                inline=False,
            )
            embed.add_field(
                name="✅ 답변",
                value=(
                    "우선 기존 인증을 조회합니다.\n"
                    "아래 버튼을 눌러 인증 시 사용되는 마이페이지 링크를 입력해주세요."
                ),
                inline=False,
            )
            await interaction.response.edit_message(embed=embed, view=TicketAuthDuplicateView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌", row=2)
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthResponseView(discord.ui.View):
        def __init__(self, url: str):
            super().__init__(timeout=None)
            self.url = url

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="관리자에게 문의하기", style=discord.ButtonStyle.success, emoji="💬")
        async def contact_admin(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != member.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 요청자만 사용할 수 있습니다.", ephemeral=True)
                return

            if timeout_task and not timeout_task.done():
                timeout_task.cancel()

            await channel.set_permissions(member, send_messages=True, attach_files=True, embed_links=True)
            await interaction.response.edit_message(embed=inquiry_embed, view=ticket_control_view_factory())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthTextView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthTransferView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="마이페이지 링크 입력", style=discord.ButtonStyle.primary, emoji="🔗")
        async def enter_link(self, button: discord.ui.Button, interaction: discord.Interaction):
            await interaction.response.send_modal(AuthLinkModal(flow="transfer"))

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthDuplicateView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="마이페이지 링크 입력", style=discord.ButtonStyle.primary, emoji="🔗")
        async def enter_link(self, button: discord.ui.Button, interaction: discord.Interaction):
            await interaction.response.send_modal(AuthLinkModal(flow="duplicate"))

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthTransferResultView(discord.ui.View):
        def __init__(self, result_text: str):
            super().__init__(timeout=None)
            self.result_text = result_text

        @discord.ui.button(label="관리자에게 문의하기", style=discord.ButtonStyle.success, emoji="💬")
        async def contact_admin(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != member.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 요청자만 사용할 수 있습니다.", ephemeral=True)
                return

            if timeout_task and not timeout_task.done():
                timeout_task.cancel()

            await channel.set_permissions(member, send_messages=True, attach_files=True, embed_links=True)
            result_embed = discord.Embed(
                title="🔍 인증 검색 결과",
                description=self.result_text,
                color=discord.Color.blurple(),
            )
            await channel.send(embed=result_embed)
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="✅ 관리자에게 문의하기",
                    description=(
                        "채팅이 열렸습니다. 아래에 캡쳐본을 전송해주세요.\n"
                        "캡쳐본이 없으면 관리자가 확인 후 문의를 종료합니다."
                    ),
                    color=discord.Color.green(),
                ),
                view=TicketTransferCloseView(),
            )

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketTransferCloseView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthDuplicateResultView(discord.ui.View):
        def __init__(self, result_text: str, discord_ids: list[int]):
            super().__init__(timeout=None)
            self.result_text = result_text
            self.discord_ids = discord_ids

        @discord.ui.button(label="예", style=discord.ButtonStyle.success, emoji="✅")
        async def yes_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            embed = discord.Embed(
                title="✅ 인증 안내",
                description=(
                    "해당 계정으로 접속해서 **인증 관리 → 인증 취소**를 진행 해주시거나 "
                    "카단서버를 탈퇴해 주세요.\n"
                    "위 진행이 불가할 시 관리자에게 문의하기 버튼을 눌러 자세한 설명을 남겨주세요.\n"
                    "아무런 메시지가 없을 시 관리자가 확인 후 문의를 종료합니다."
                ),
                color=discord.Color.blurple(),
            )
            await interaction.response.edit_message(embed=embed, view=TicketAuthDuplicateYesView(self.result_text))

        @discord.ui.button(label="아니오", style=discord.ButtonStyle.danger, emoji="❌")
        async def no_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()

            await channel.set_permissions(member, send_messages=True, attach_files=True, embed_links=True)

            # ✅ 기존에 인증 중인 사용자들에게 동일 채널 권한 부여
            target_mentions = []
            for discord_id in self.discord_ids:
                target = guild.get_member(discord_id)
                if target is None:
                    try:
                        target = await guild.fetch_member(discord_id)
                    except discord.NotFound:
                        target = None
                if target:
                    target_mentions.append(target.mention)
                    await channel.set_permissions(
                        target,
                        view_channel=True,
                        send_messages=True,
                        attach_files=True,
                        embed_links=True,
                    )
                else:
                    target_mentions.append(f"<@{discord_id}>")

            target_label = " ".join(target_mentions) if target_mentions else "인증 대상자"

            await channel.send(
                f"🔔 문의자가 인증 중인 계정에 중복인증을 신청했습니다.\n"
                f"{member.mention} 님이 {target_label} 님이 인증 중인 계정에 중복인증을 신청했습니다.\n"
                "두 분이서 대화 나눈 후 관리자가 판단하여 인증 기록을 관리할 예정입니다.\n"
                "문의 종료는 관리자만 누를 수 있습니다."
            )

            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🛡️ 중복 인증 안내",
                    description="인증 대상자와 대화를 진행해 주세요.",
                    color=discord.Color.orange(),
                ),
                view=TicketAuthAdminCloseView(),
            )

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthDuplicateYesView(discord.ui.View):
        def __init__(self, result_text: str):
            super().__init__(timeout=None)
            self.result_text = result_text

        @discord.ui.button(label="관리자에게 문의하기", style=discord.ButtonStyle.success, emoji="💬")
        async def contact_admin(self, button: discord.ui.Button, interaction: discord.Interaction):
            if interaction.user.id != member.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 요청자만 사용할 수 있습니다.", ephemeral=True)
                return

            if timeout_task and not timeout_task.done():
                timeout_task.cancel()

            await channel.set_permissions(member, send_messages=True, attach_files=True, embed_links=True)
            result_embed = discord.Embed(
                title="🔍 인증 검색 결과",
                description=self.result_text,
                color=discord.Color.blurple(),
            )
            await channel.send(embed=result_embed)
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="✅ 관리자에게 문의하기",
                    description=(
                        "채팅이 열렸습니다. 상황을 설명해 주세요.\n"
                        "아무런 메시지가 없을 시 관리자가 확인 후 문의를 종료합니다."
                    ),
                    color=discord.Color.green(),
                ),
                view=TicketTransferCloseView(),
            )

        @discord.ui.button(label="뒤로가기", style=discord.ButtonStyle.secondary, emoji="↩️")
        async def back_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await schedule_timeout("close")
            await interaction.response.edit_message(embed=auth_embed, view=TicketAuthView())

        @discord.ui.button(label="문의 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    class TicketAuthAdminCloseView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="인증 종료", style=discord.ButtonStyle.danger, emoji="⛔")
        async def admin_close(self, button: discord.ui.Button, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 관리자만 사용할 수 있습니다.", ephemeral=True)
                return
            if timeout_task and not timeout_task.done():
                timeout_task.cancel()
            await close_ticket(interaction)

    def extract_member_no_from_link(link: str) -> Optional[str]:
        cleaned = link.strip()
        if "://" in cleaned:
            cleaned = cleaned.split("://", 1)[1]
        cleaned = cleaned.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        if not cleaned.startswith("profile.onstove.com/"):
            return None
        path = cleaned.split("profile.onstove.com/", 1)[1]
        member_no = path.split("/")[-1] if path else ""
        return member_no if member_no.isdigit() else None

    class AuthLinkModal(discord.ui.Modal):
        def __init__(self, flow: str):
            super().__init__(title="마이페이지 링크 입력")
            self.flow = flow
            self.link_input = discord.ui.InputText(
                label="마이페이지 링크",
                placeholder="https://profile.onstove.com/ko/84599446",
                style=discord.InputTextStyle.short,
            )
            self.add_item(self.link_input)

        async def callback(self, interaction: discord.Interaction):
            await schedule_timeout("close")
            link = self.link_input.value.strip()
            member_no = extract_member_no_from_link(link)

            if not member_no:
                await interaction.response.send_message(
                    "❌ 올바른 마이페이지 링크를 입력해주세요.",
                    ephemeral=True,
                )
                return

            result_text, discord_ids = lookup_auth_records(member_no)
            lookup_embed = discord.Embed(
                title="🔍 인증 검색 결과",
                color=discord.Color.blurple(),
            )
            lookup_embed.add_field(name="🔢 조회 번호", value=member_no, inline=False)
            lookup_embed.add_field(name="📋 결과", value=result_text, inline=False)

            if self.flow == "transfer":
                lookup_embed.add_field(
                    name="📎 안내",
                    value=(
                        "해당 계정의 양도 및 구매 시 **판매자/본 소유주와의 거래 메시지 또는 DM, "
                        "거래 내역 등** 양도 받은 사실이 적혀있는 증거를 캡쳐해 "
                        "아래 관리자에게 문의하기 버튼을 눌러 전송해주세요.\n"
                        "관리자가 확인 후 캡처본이 없을 시 문의를 종료합니다."
                    ),
                    inline=False,
                )
                view = TicketAuthTransferResultView(result_text)
            else:
                lookup_embed.add_field(
                    name="❓ 본인 소유 여부",
                    value="해당 계정이 본인 소유입니까? 아래 버튼을 선택해 주세요.",
                    inline=False,
                )
                view = TicketAuthDuplicateResultView(result_text, discord_ids)

            await interaction.response.edit_message(embed=lookup_embed, view=view)

    chatbot_message = await channel.send(content=member.mention, embed=chatbot_embed, view=TicketChatbotView())
    await schedule_timeout("delete")
