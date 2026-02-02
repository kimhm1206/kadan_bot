import asyncio
import re
import discord
from datetime import datetime
from typing import Optional
from utils.function import get_conn, get_setting_cached
import os
import aiohttp
from block.block_ticket import BlockTicketView  # ✅ 차단 해제 뷰
import zipfile

ICON_MAP = {
    "문의": "📩",
    "신고": "🚨",
    "인증": "🔑",
    "차단": "📛"
}


async def archive_ticket_channel(
    channel: discord.TextChannel,
    deleter: discord.abc.User,
    log_channel: Optional[discord.TextChannel],
    ticket_type: Optional[str],
    owner_label: Optional[str],
) -> None:
    """티켓 채널 메시지를 정리하고 로그에 남긴 뒤 채널을 삭제합니다."""

    icon = ICON_MAP.get(ticket_type or "", "📌")
    ticket_name = ticket_type or "티켓"
    owner_label = owner_label or "알 수 없음"
    deleter_mention = (
        deleter.mention
        if isinstance(deleter, (discord.Member, discord.User))
        else getattr(deleter, "mention", "알 수 없음")
    )

    all_messages = []
    image_attachments = []  # (url, safe_filename)

    async for msg in channel.history(limit=None, oldest_first=True):
        content = msg.content or ""
        line = f"[{msg.created_at.strftime('%Y-%m-%d %H:%M')}] {msg.author.display_name}: {content}"
        if msg.attachments:
            for att in msg.attachments:
                ext = att.filename.lower().split(".")[-1]
                safe_name = f"ticket_img-{channel.id}-{att.id}.{ext}"
                if ext in ["png", "jpg", "jpeg", "gif", "webp"]:
                    image_attachments.append((att.url, safe_name))
                    line += f" (📎 이미지 첨부: {att.filename})"
                else:
                    line += f" (📎 첨부파일: {att.filename} → {att.url})"
        all_messages.append(line)

    log_embed = discord.Embed(
        title=f"{icon} {ticket_name} 티켓 삭제됨",
        description=(
            f"채널: {channel.name}\n"
            f"개설자: {owner_label}\n"
            f"삭제자: {deleter_mention}"
        ),
        color=discord.Color.dark_gray(),
    )

    preview_messages = all_messages if len(all_messages) <= 20 else all_messages[-20:]
    preview_label = "📜 티켓 메시지 로그" if len(all_messages) <= 20 else "📜 최근 20개 메시지"
    preview_body = "\n".join(preview_messages) if preview_messages else "메시지 없음"
    force_attachment = len(preview_body) > 1024

    if force_attachment:
        first_line = preview_messages[0] if preview_messages else "메시지 없음"
        if len(first_line) > 1000:
            first_line = first_line[:1000] + "..."
        preview_body = first_line + "\n\n전체 로그는 첨부 파일을 확인하세요."

    log_embed.add_field(
        name=preview_label,
        value=preview_body[:1024] if preview_body else "메시지 없음",
        inline=False,
    )

    files = []      # 디스코드 전송용 File 객체
    tmp_files = []  # 로컬 임시 파일 경로

    try:
        async with aiohttp.ClientSession() as session:
            for url, safe_name in image_attachments:
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            with open(safe_name, "wb") as f:
                                f.write(await resp.read())
                            tmp_files.append(safe_name)
                except Exception as e:
                    print(f"⚠️ 이미지 다운로드 실패: {url} ({e})")

        image_file_paths = list(tmp_files)

        needs_text_attachment = len(all_messages) > 20 or force_attachment
        full_log_text = "\n".join(all_messages)

        if len(image_attachments) == 0:
            if needs_text_attachment:
                txt_name = f"ticket_log-{channel.id}.txt"
                with open(txt_name, "w", encoding="utf-8") as f:
                    f.write(full_log_text)
                zip_name = f"ticket_log-{channel.id}.zip"
                with zipfile.ZipFile(zip_name, "w") as zipf:
                    zipf.write(txt_name)
                files.append(discord.File(zip_name))
                tmp_files.extend([txt_name, zip_name])

        elif len(image_attachments) == 1:
            last_img = image_file_paths[-1]
            log_embed.set_image(url=f"attachment://{os.path.basename(last_img)}")
            files.append(discord.File(last_img))
            if needs_text_attachment:
                txt_name = f"ticket_log-{channel.id}.txt"
                with open(txt_name, "w", encoding="utf-8") as f:
                    f.write(full_log_text)
                zip_name = f"ticket_log-{channel.id}.zip"
                with zipfile.ZipFile(zip_name, "w") as zipf:
                    zipf.write(txt_name)
                files.append(discord.File(zip_name))
                tmp_files.extend([txt_name, zip_name])

        else:
            zip_name = f"ticket_log-{channel.id}.zip"
            with zipfile.ZipFile(zip_name, "w") as zipf:
                if needs_text_attachment:
                    txt_name = f"ticket_log-{channel.id}.txt"
                    with open(txt_name, "w", encoding="utf-8") as f:
                        f.write(full_log_text)
                    zipf.write(txt_name)
                    tmp_files.append(txt_name)
                for img in tmp_files:
                    zipf.write(img)
            files.append(discord.File(zip_name))
            tmp_files.append(zip_name)

            last_img = image_file_paths[-1] if image_file_paths else None
            if last_img:
                log_embed.set_image(url=f"attachment://{os.path.basename(last_img)}")
                files.append(discord.File(last_img))

        if log_channel:
            await log_channel.send(embed=log_embed, files=files)

        for file in files:
            try:
                file.close()
            except Exception:
                pass

    finally:
        for f in tmp_files:
            try:
                os.remove(f)
            except Exception as e:
                print(f"⚠️ 임시 파일 삭제 실패: {e}")

    await channel.delete(reason=f"{ticket_name} 티켓 정리 및 삭제")

async def create_ticket(member: discord.Member, ticket_type: str, block_data: list = None):
    """
    티켓 채널 생성
    :param member: 티켓 개설자
    :param ticket_type: "문의" / "신고" / "인증" / "차단"
    :param block_data: 차단 데이터(details 리스트)
    """
    guild = member.guild
    guild_id = guild.id

    # ✅ 카테고리 & 로그 채널
    category_id = get_setting_cached(guild_id, "ticket_category")
    log_channel_id = get_setting_cached(guild_id, "ticket_log_channel")

    category = guild.get_channel(int(category_id)) if category_id else None
    log_channel = guild.get_channel(int(log_channel_id)) if log_channel_id else None
    if log_channel and not isinstance(log_channel, discord.TextChannel):
        log_channel = None

    # ✅ 채널 이름
    now = datetime.now().strftime("%y%m%d%H%M")
    icon = ICON_MAP.get(ticket_type, "📌")
    channel_name = f"{icon}-{ticket_type}-{now}-{member.id}"

    # ✅ 권한
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        member: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, embed_links=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
    }

    # ✅ 채널 생성
    channel = await guild.create_text_channel(
        name=channel_name,
        category=category,
        overwrites=overwrites,
        reason=f"{ticket_type} 티켓 자동 생성"
    )

    # 🔹 기본 환영 임베드
    embed = discord.Embed(
        title=f"{icon} {ticket_type} 티켓 생성됨",
        description=(
            f"{member.mention} 님, 관련 내용을 아래에 작성해 주세요.\n\n"
            "❌ 문의 사항 종료시 아래 버튼을 눌러 티켓을 종료할 수 있습니다."
        ),
        color=discord.Color.blue()
    )

    async def close_ticket_message(message: discord.Message, allow_delete: bool = True):
        await channel.edit(name=f"종료된-{channel.name}")
        await channel.set_permissions(member, view_channel=False)

        description = (
            "🔒 이 문의는 종료되었습니다.\n\n"
            "📌 메모를 남긴 뒤 아래 버튼으로 채널을 삭제할 수 있습니다. \n"
            "마지막 20개의 메시지만 로그에 남습니다."
        )
        if not allow_delete:
            description = "🔒 이 문의는 종료되었습니다."

        delete_view = TicketDeleteView(member, ticket_type, log_channel) if allow_delete else None
        await message.edit(
            embed=discord.Embed(
                title=f"{icon} {ticket_type} 티켓 종료됨",
                description=description,
                color=discord.Color.red(),
            ),
            view=delete_view,
        )

    async def close_ticket(interaction: discord.Interaction, allow_delete: bool = True):
        # 관리자 또는 개설자만 닫기 가능
        if interaction.user.id != member.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("⚠️ 이 티켓을 닫을 권한이 없습니다.", ephemeral=True)
            return

        await interaction.response.send_message("⏳ 티켓이 종료되었습니다.", ephemeral=True)
        await close_ticket_message(interaction.message, allow_delete=allow_delete)

    # 🔹 닫기/삭제 버튼 뷰
    class TicketControlView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(label="티켓 종료", style=discord.ButtonStyle.danger, emoji="❌")
        async def close_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            await close_ticket(interaction)

    class TicketDeleteView(discord.ui.View):
        def __init__(self, ticket_owner: discord.Member, t_type: str, log_ch: discord.TextChannel):
            super().__init__(timeout=None)
            self.owner = ticket_owner
            self.t_type = t_type
            self.log_ch = log_ch
            
        @discord.ui.button(label="채널 삭제", style=discord.ButtonStyle.danger, emoji="🗑️")
        async def delete_button(self, button: discord.ui.Button, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("⚠️ 관리자만 채널을 삭제할 수 있습니다.", ephemeral=True)
                return

            # ✅ Defer (시간 오래 걸릴 수 있음)
            await interaction.response.defer(ephemeral=True)

            # 삭제를 시작했다는 안내를 먼저 남겨 채널 삭제 후 Unknown Channel 오류를 방지
            try:
                await interaction.followup.send("🗑️ 티켓 채널 삭제를 시작합니다.", ephemeral=True)
            except Exception:
                pass

            try:
                await archive_ticket_channel(
                    channel=channel,
                    deleter=interaction.user,
                    log_channel=self.log_ch,
                    ticket_type=self.t_type,
                    owner_label=self.owner.mention,
                )
            except discord.Forbidden:
                await interaction.followup.send("⚠️ 채널 삭제 권한이 부족합니다.", ephemeral=True)
                return
            except Exception as e:
                await interaction.followup.send(
                    f"⚠️ 채널 삭제 중 오류가 발생했습니다: {e}",
                    ephemeral=True,
                )
                return


    # ✅ 기본 임베드 + 컨트롤 뷰 전송
    if ticket_type in ["문의", "인증"]:
        await channel.set_permissions(member, send_messages=False)

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

        auth_tip_text = (
            "1) 아래 영상을 보고 제시도 해주세요.\n"
            "2) 제시도 후에도 안될 시 **봇이 응답하는 화면을 캡쳐**해 주세요.\n"
            "3) **관리자에게 문의하기** 버튼을 눌러 캡쳐본을 전송해주세요.\n\n"
            "📎 **캡쳐본이 없으면 관리자가 확인 후 문의를 종료합니다.**"
        )

        def extract_member_no(input_text: str) -> str | None:
            numbers = re.findall(r"\d+", input_text)
            return numbers[-1] if numbers else None

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
            await archive_ticket_channel(
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
                await interaction.response.edit_message(embed=inquiry_embed, view=TicketControlView())

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
                await interaction.response.edit_message(embed=inquiry_embed, view=TicketControlView())

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
            if cleaned.startswith("http://") or cleaned.startswith("https://"):
                cleaned = cleaned.split("://", 1)[1]
            cleaned = cleaned.split("?", 1)[0]
            if not cleaned.startswith("profile.onstove.com/ko/"):
                return None
            member_no = cleaned.split("/")[-1]
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
    else:
        await channel.send(content=member.mention, embed=embed, view=TicketControlView())

    # ✅ 차단 타입일 경우 추가 임베드/뷰
    if ticket_type == "차단" and block_data:
        reason_list = []
        for b in block_data:
            gid = int(b["guild_id"])
            server_name = get_setting_cached(gid, "server") or str(gid)

            blocked_by_id = b.get("blocked_by")
            if blocked_by_id and member.guild.me and blocked_by_id == member.guild.me.id:
                blocked_by = "[봇]"
            elif blocked_by_id:
                blocked_by = f"<@{blocked_by_id}>"
            else:
                blocked_by = "알 수 없음"

            reason_list.append(
                f"[서버:{server_name}] {b['data_type']}={b['value']} "
                f"(사유:{b['reason']}, 차단자:{blocked_by})"
            )

        msg = "🚫 차단된 사용자로 확인되었습니다.\n\n"
        msg += "**차단 내역:**\n" + "\n".join(reason_list)
        msg += "\n\n관리자와 소통하여 이의 제기를 진행해주세요."

        await channel.send(
            content=f"{member.mention}\n{msg}",
            view=BlockTicketView(block_data)  # ✅ 기존 unblock 로직 그대로 사용
        )

    return channel
