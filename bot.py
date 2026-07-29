# -*- coding: utf-8 -*-
"""
VALORANT Lineup Discord Bot
- 完全以常駐訊息、按鈕、下拉選單與 Modal 操作
- SQLite 儲存資料
- discord.py 2.x
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 基本設定
# ============================================================

BOT_TOKEN: Final[str] = os.getenv("DISCORD_BOT_TOKEN", "").strip()
UPLOAD_CHANNEL_ID: Final[int] = int(os.getenv("UPLOAD_CHANNEL_ID", "0"))
WATCH_CHANNEL_ID: Final[int] = int(os.getenv("WATCH_CHANNEL_ID", "0"))
DATABASE_PATH: Final[Path] = Path(os.getenv("DATABASE_PATH", "lineups.db"))

# 可選：限制只有指定身分組能上傳。未設定或設為 0 時，所有人皆可上傳。
UPLOAD_ROLE_ID: Final[int] = int(os.getenv("UPLOAD_ROLE_ID", "0"))

EMBED_COLOR: Final[int] = 0xFF4655
RESULTS_PER_PAGE: Final[int] = 8

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("valorant-lineup-bot")


# ============================================================
# 官方中英文對照清單
#
# 注意：Discord 的 String Select 單一選單最多只能放 25 個 options，
# 但目前特務共 26 位，因此必須先選定位，再選特務。
# 這仍然是純下拉選單操作，不需要輸入任何指令。
# ============================================================

AGENTS_BY_ROLE: Final[dict[str, tuple[str, ...]]] = {
    "決鬥者 (Duelist)": (
        "婕提 (Jett)",
        "蕾娜 (Reyna)",
        "芮茲 (Raze)",
        "菲尼克斯 (Phoenix)",
        "夜戮 (Yoru)",
        "妮虹 (Neon)",
        "離索 (Iso)",
    ),
    "先鋒 (Initiator)": (
        "蘇法 (Sova)",
        "叛奇 (Breach)",
        "絲凱 (Skye)",
        "KAY/O (KAY/O)",
        "菲德 (Fade)",
        "蓋克 (Gekko)",
        "戴侯 (Tejo)",
    ),
    "控場者 (Controller)": (
        "布史東 (Brimstone)",
        "薇蝮 (Viper)",
        "歐門 (Omen)",
        "亞星卓 (Astra)",
        "哈泊 (Harbor)",
        "珂樂芙 (Clove)",
    ),
    "守衛 (Sentinel)": (
        "聖祈 (Sage)",
        "瑟符 (Cypher)",
        "愷宙 (Killjoy)",
        "錢博爾 (Chamber)",
        "蒂羅 (Deadlock)",
        "薇絲 (Vyse)",
    ),
}

MAPS: Final[tuple[str, ...]] = (
    "頂峰亭閣 (District)",
    "晶蝕之地 (Glitch)",
    "深窟幽境 (Abyss)",
    "日落之城 (Sunset)",
    "蓮華古城 (Lotus)",
    "深海遺珠 (Pearl)",
    "天漠之峽 (Fracture)",
    "熱帶樂園 (Breeze)",
    "極地寒港 (Icebox)",
    "義境空島 (Ascent)",
    "雙塔迷城 (Split)",
    "遺落境地 (Haven)",
    "劫境之地 (Bind)",
)

ALL_AGENTS: Final[tuple[str, ...]] = tuple(
    agent for agents in AGENTS_BY_ROLE.values() for agent in agents
)


# ============================================================
# 資料模型
# ============================================================

@dataclass(slots=True, frozen=True)
class Lineup:
    id: int
    map_name: str
    agent_name: str
    title: str
    video_url: str
    uploader_id: int
    uploader_name: str
    created_at: str


# ============================================================
# SQLite 資料庫
# ============================================================

class Database:
    """使用 asyncio.to_thread 包裝 sqlite3，避免阻塞 Discord event loop。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS lineups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    map_name TEXT NOT NULL,
                    agent_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    video_url TEXT NOT NULL,
                    uploader_id INTEGER NOT NULL,
                    uploader_name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_lineups_map_agent
                ON lineups(map_name, agent_name);

                CREATE TABLE IF NOT EXISTS bot_settings (
                    setting_key TEXT PRIMARY KEY,
                    setting_value TEXT NOT NULL
                );
                """
            )

    async def add_lineup(
        self,
        *,
        map_name: str,
        agent_name: str,
        title: str,
        video_url: str,
        uploader_id: int,
        uploader_name: str,
    ) -> int:
        return await asyncio.to_thread(
            self._add_lineup_sync,
            map_name,
            agent_name,
            title,
            video_url,
            uploader_id,
            uploader_name,
        )

    def _add_lineup_sync(
        self,
        map_name: str,
        agent_name: str,
        title: str,
        video_url: str,
        uploader_id: int,
        uploader_name: str,
    ) -> int:
        with self._connect() as db:
            cursor = db.execute(
                """
                INSERT INTO lineups (
                    map_name, agent_name, title, video_url,
                    uploader_id, uploader_name
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    map_name,
                    agent_name,
                    title,
                    video_url,
                    uploader_id,
                    uploader_name,
                ),
            )
            return int(cursor.lastrowid)

    async def get_lineups(self, map_name: str, agent_name: str) -> list[Lineup]:
        return await asyncio.to_thread(
            self._get_lineups_sync, map_name, agent_name
        )

    def _get_lineups_sync(
        self, map_name: str, agent_name: str
    ) -> list[Lineup]:
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT id, map_name, agent_name, title, video_url,
                       uploader_id, uploader_name, created_at
                FROM lineups
                WHERE map_name = ? AND agent_name = ?
                ORDER BY id DESC
                """,
                (map_name, agent_name),
            ).fetchall()

        return [Lineup(**dict(row)) for row in rows]

    async def get_setting(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get_setting_sync, key)

    def _get_setting_sync(self, key: str) -> str | None:
        with self._connect() as db:
            row = db.execute(
                "SELECT setting_value FROM bot_settings WHERE setting_key = ?",
                (key,),
            ).fetchone()
        return str(row["setting_value"]) if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await asyncio.to_thread(self._set_setting_sync, key, value)

    def _set_setting_sync(self, key: str, value: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO bot_settings(setting_key, setting_value)
                VALUES (?, ?)
                ON CONFLICT(setting_key)
                DO UPDATE SET setting_value = excluded.setting_value
                """,
                (key, value),
            )


database = Database(DATABASE_PATH)


# ============================================================
# 共用工具
# ============================================================

def make_options(items: tuple[str, ...]) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(label=item, value=item)
        for item in items
    ]


def is_valid_video_url(value: str) -> bool:
    """
    接受一般 http / https 網址。
    不只綁定 YouTube，亦可支援 Instagram、Streamable 等平台。
    """
    try:
        parsed = urlparse(value.strip())
    except ValueError:
        return False

    return (
        parsed.scheme in {"http", "https"}
        and bool(parsed.netloc)
        and "." in parsed.netloc
        and " " not in value
    )


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def user_can_upload(user: discord.abc.User) -> bool:
    if UPLOAD_ROLE_ID == 0:
        return True

    if not isinstance(user, discord.Member):
        return False

    return any(role.id == UPLOAD_ROLE_ID for role in user.roles)


async def safe_ephemeral_error(
    interaction: discord.Interaction,
    message: str,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


# ============================================================
# 上傳流程
# 1. 常駐面板按鈕
# 2. 私人下拉選擇地圖、定位、特務
# 3. 按下一步後開啟 Modal
# ============================================================

class UploadMapSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="① 選擇地圖",
            min_values=1,
            max_values=1,
            options=make_options(MAPS),
            custom_id="lineup:upload:map",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, UploadSelectionView)
        view.selected_map = self.values[0]
        view.refresh()
        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view,
        )


class UploadRoleSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="② 選擇特務定位",
            min_values=1,
            max_values=1,
            options=make_options(tuple(AGENTS_BY_ROLE.keys())),
            custom_id="lineup:upload:role",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, UploadSelectionView)
        view.selected_role = self.values[0]
        view.selected_agent = None
        view.refresh()
        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view,
        )


class UploadAgentSelect(discord.ui.Select):
    def __init__(self, role_name: str | None) -> None:
        if role_name:
            options = make_options(AGENTS_BY_ROLE[role_name])
            disabled = False
            placeholder = "③ 選擇特務"
        else:
            options = [
                discord.SelectOption(
                    label="請先選擇定位",
                    value="__disabled__",
                )
            ]
            disabled = True
            placeholder = "③ 請先選擇特務定位"

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            disabled=disabled,
            custom_id="lineup:upload:agent",
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, UploadSelectionView)
        view.selected_agent = self.values[0]
        view.refresh()
        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view,
        )


class UploadSelectionView(discord.ui.View):
    def __init__(self, owner_id: int) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.selected_map: str | None = None
        self.selected_role: str | None = None
        self.selected_agent: str | None = None
        self.refresh()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "這是其他使用者的私人上傳面板。",
                ephemeral=True,
            )
            return False
        return True

    def refresh(self) -> None:
        self.clear_items()
        self.add_item(UploadMapSelect())
        self.add_item(UploadRoleSelect())
        self.add_item(UploadAgentSelect(self.selected_role))

        next_button = discord.ui.Button(
            label="下一步：填寫影片資料",
            emoji="📝",
            style=discord.ButtonStyle.primary,
            custom_id="lineup:upload:open_modal",
            disabled=not (self.selected_map and self.selected_agent),
            row=3,
        )
        next_button.callback = self.open_modal
        self.add_item(next_button)

        cancel_button = discord.ui.Button(
            label="取消",
            style=discord.ButtonStyle.secondary,
            custom_id="lineup:upload:cancel",
            row=3,
        )
        cancel_button.callback = self.cancel
        self.add_item(cancel_button)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="📤 上傳 VALORANT Lineup",
            description=(
                "請依序選擇地圖、特務定位與特務，"
                "完成後按下「下一步」。"
            ),
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="地圖",
            value=self.selected_map or "尚未選擇",
            inline=False,
        )
        embed.add_field(
            name="特務",
            value=self.selected_agent or "尚未選擇",
            inline=False,
        )
        embed.set_footer(text="此操作介面只有你看得到，5 分鐘後失效。")
        return embed

    async def open_modal(self, interaction: discord.Interaction) -> None:
        if not self.selected_map or not self.selected_agent:
            await interaction.response.send_message(
                "請先選完地圖與特務。",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            LineupUploadModal(
                map_name=self.selected_map,
                agent_name=self.selected_agent,
            )
        )

    async def cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="已取消上傳。",
            embed=None,
            view=None,
        )

    async def on_timeout(self) -> None:
        self.stop()


class LineupUploadModal(
    discord.ui.Modal,
    title="填寫 Lineup 資料",
):
    video_url = discord.ui.TextInput(
        label="影片連結",
        placeholder="https://youtube.com/...、https://instagram.com/...",
        style=discord.TextStyle.short,
        min_length=8,
        max_length=500,
        required=True,
    )

    lineup_title = discord.ui.TextInput(
        label="標題／說明",
        placeholder="例如：A 點防守偵查箭",
        style=discord.TextStyle.paragraph,
        min_length=2,
        max_length=300,
        required=True,
    )

    def __init__(self, *, map_name: str, agent_name: str) -> None:
        super().__init__(timeout=300, custom_id="lineup:upload:modal")
        self.map_name = map_name
        self.agent_name = agent_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        url = str(self.video_url).strip()
        title = str(self.lineup_title).strip()

        if not user_can_upload(interaction.user):
            await interaction.response.send_message(
                "你沒有上傳 Lineup 的權限。",
                ephemeral=True,
            )
            return

        if self.map_name not in MAPS or self.agent_name not in ALL_AGENTS:
            await interaction.response.send_message(
                "地圖或特務資料無效，請重新操作。",
                ephemeral=True,
            )
            return

        if not is_valid_video_url(url):
            await interaction.response.send_message(
                "影片連結格式不正確，請輸入完整的 http:// 或 https:// 網址。",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        lineup_id = await database.add_lineup(
            map_name=self.map_name,
            agent_name=self.agent_name,
            title=title,
            video_url=url,
            uploader_id=interaction.user.id,
            uploader_name=str(interaction.user),
        )

        embed = discord.Embed(
            title="✅ Lineup 上傳成功",
            color=0x57F287,
        )
        embed.add_field(name="編號", value=f"`#{lineup_id}`", inline=True)
        embed.add_field(name="地圖", value=self.map_name, inline=False)
        embed.add_field(name="特務", value=self.agent_name, inline=False)
        embed.add_field(name="標題", value=title, inline=False)
        embed.add_field(
            name="影片",
            value=f"[點此開啟影片]({url})",
            inline=False,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
    ) -> None:
        logger.exception("Lineup Modal 發生錯誤", exc_info=error)
        await safe_ephemeral_error(
            interaction,
            "上傳時發生錯誤，請稍後再試。",
        )


class PersistentUploadPanel(discord.ui.View):
    """timeout=None + 固定 custom_id，讓機器人重啟後按鈕仍可使用。"""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="上傳 Lineup",
        emoji="📤",
        style=discord.ButtonStyle.primary,
        custom_id="lineup:persistent:upload",
    )
    async def upload_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not user_can_upload(interaction.user):
            await interaction.response.send_message(
                "你沒有上傳 Lineup 的權限。",
                ephemeral=True,
            )
            return

        view = UploadSelectionView(owner_id=interaction.user.id)
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


# ============================================================
# 查詢流程
#
# 常駐查詢面板提供地圖與定位下拉選單。
# 選擇任一項後，機器人會開啟該使用者專屬的私人查詢面板，
# 避免多人同時操作同一則常駐訊息時互相覆蓋選項。
# ============================================================

class PublicMapSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="選擇地圖，開啟私人查詢面板",
            min_values=1,
            max_values=1,
            options=make_options(MAPS),
            custom_id="lineup:query:public_map",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = QuerySessionView(
            owner_id=interaction.user.id,
            selected_map=self.values[0],
        )
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PublicRoleSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="選擇特務定位，開啟私人查詢面板",
            min_values=1,
            max_values=1,
            options=make_options(tuple(AGENTS_BY_ROLE.keys())),
            custom_id="lineup:query:public_role",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = QuerySessionView(
            owner_id=interaction.user.id,
            selected_role=self.values[0],
        )
        await interaction.response.send_message(
            embed=view.build_embed(),
            view=view,
            ephemeral=True,
        )


class PersistentQueryPanel(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(PublicMapSelect())
        self.add_item(PublicRoleSelect())


class QueryMapSelect(discord.ui.Select):
    def __init__(self, selected_map: str | None) -> None:
        options = []
        for map_name in MAPS:
            options.append(
                discord.SelectOption(
                    label=map_name,
                    value=map_name,
                    default=(map_name == selected_map),
                )
            )

        super().__init__(
            placeholder="① 選擇地圖",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="lineup:query:session_map",
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, QuerySessionView)
        view.selected_map = self.values[0]
        view.page = 0
        view.refresh()
        await view.update_results(interaction)


class QueryRoleSelect(discord.ui.Select):
    def __init__(self, selected_role: str | None) -> None:
        options = []
        for role_name in AGENTS_BY_ROLE:
            options.append(
                discord.SelectOption(
                    label=role_name,
                    value=role_name,
                    default=(role_name == selected_role),
                )
            )

        super().__init__(
            placeholder="② 選擇特務定位",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="lineup:query:session_role",
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, QuerySessionView)
        view.selected_role = self.values[0]
        view.selected_agent = None
        view.results = []
        view.page = 0
        view.refresh()
        await interaction.response.edit_message(
            embed=view.build_embed(),
            view=view,
        )


class QueryAgentSelect(discord.ui.Select):
    def __init__(
        self,
        selected_role: str | None,
        selected_agent: str | None,
    ) -> None:
        if selected_role:
            options = [
                discord.SelectOption(
                    label=agent,
                    value=agent,
                    default=(agent == selected_agent),
                )
                for agent in AGENTS_BY_ROLE[selected_role]
            ]
            disabled = False
            placeholder = "③ 選擇特務並立即查詢"
        else:
            options = [
                discord.SelectOption(
                    label="請先選擇定位",
                    value="__disabled__",
                )
            ]
            disabled = True
            placeholder = "③ 請先選擇特務定位"

        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            disabled=disabled,
            custom_id="lineup:query:session_agent",
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        assert isinstance(view, QuerySessionView)
        view.selected_agent = self.values[0]
        view.page = 0
        view.refresh()
        await view.update_results(interaction)


class QuerySessionView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        selected_map: str | None = None,
        selected_role: str | None = None,
    ) -> None:
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.selected_map = selected_map
        self.selected_role = selected_role
        self.selected_agent: str | None = None
        self.results: list[Lineup] = []
        self.page = 0
        self.refresh()

    async def interaction_check(
        self,
        interaction: discord.Interaction,
    ) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "這是其他使用者的私人查詢面板。",
                ephemeral=True,
            )
            return False
        return True

    def refresh(self) -> None:
        self.clear_items()
        self.add_item(QueryMapSelect(self.selected_map))
        self.add_item(QueryRoleSelect(self.selected_role))
        self.add_item(
            QueryAgentSelect(self.selected_role, self.selected_agent)
        )

        total_pages = max(
            1,
            (len(self.results) + RESULTS_PER_PAGE - 1)
            // RESULTS_PER_PAGE,
        )

        previous_button = discord.ui.Button(
            label="上一頁",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            disabled=(self.page <= 0 or not self.results),
            custom_id="lineup:query:previous",
            row=3,
        )
        previous_button.callback = self.previous_page
        self.add_item(previous_button)

        next_button = discord.ui.Button(
            label="下一頁",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            disabled=(
                not self.results
                or self.page >= total_pages - 1
            ),
            custom_id="lineup:query:next",
            row=3,
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

        close_button = discord.ui.Button(
            label="關閉",
            style=discord.ButtonStyle.danger,
            custom_id="lineup:query:close",
            row=3,
        )
        close_button.callback = self.close
        self.add_item(close_button)

    async def update_results(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if self.selected_map and self.selected_agent:
            await interaction.response.defer()
            self.results = await database.get_lineups(
                self.selected_map,
                self.selected_agent,
            )
            self.page = 0
            self.refresh()
            await interaction.edit_original_response(
                embed=self.build_embed(),
                view=self,
            )
        else:
            await interaction.response.edit_message(
                embed=self.build_embed(),
                view=self,
            )

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎯 VALORANT Lineup 查詢",
            color=EMBED_COLOR,
        )
        embed.add_field(
            name="地圖",
            value=self.selected_map or "尚未選擇",
            inline=True,
        )
        embed.add_field(
            name="特務",
            value=self.selected_agent or "尚未選擇",
            inline=True,
        )

        if not self.selected_map or not self.selected_agent:
            embed.description = (
                "請依序選擇地圖、特務定位與特務。"
                "選好特務後會自動搜尋，不需要再按查詢按鈕。"
            )
            embed.set_footer(text="私人面板將於 5 分鐘後失效。")
            return embed

        if not self.results:
            embed.description = (
                "目前沒有找到符合條件的 Lineup。\n"
                "可以到上傳面板新增第一支影片！"
            )
            embed.set_footer(text="搜尋結果：0 筆")
            return embed

        start = self.page * RESULTS_PER_PAGE
        end = start + RESULTS_PER_PAGE
        page_items = self.results[start:end]

        lines = []
        for lineup in page_items:
            safe_title = truncate(
                lineup.title.replace("[", "［").replace("]", "］"),
                180,
            )
            lines.append(
                f"**`#{lineup.id}` {safe_title}**\n"
                f"🔗 [點此開啟影片]({lineup.video_url})\n"
                f"👤 上傳者：{discord.utils.escape_markdown(lineup.uploader_name)}"
            )

        embed.description = "\n\n".join(lines)

        total_pages = (
            len(self.results) + RESULTS_PER_PAGE - 1
        ) // RESULTS_PER_PAGE
        embed.set_footer(
            text=(
                f"共 {len(self.results)} 筆｜"
                f"第 {self.page + 1}/{total_pages} 頁"
            )
        )
        return embed

    async def previous_page(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if self.page > 0:
            self.page -= 1
        self.refresh()
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    async def next_page(
        self,
        interaction: discord.Interaction,
    ) -> None:
        total_pages = max(
            1,
            (len(self.results) + RESULTS_PER_PAGE - 1)
            // RESULTS_PER_PAGE,
        )
        if self.page < total_pages - 1:
            self.page += 1
        self.refresh()
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    async def close(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(
            content="查詢面板已關閉。",
            embed=None,
            view=None,
        )

    async def on_timeout(self) -> None:
        self.stop()

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[discord.ui.View],
    ) -> None:
        logger.exception(
            "查詢 View 發生錯誤，元件=%r",
            item,
            exc_info=error,
        )
        await safe_ephemeral_error(
            interaction,
            "查詢時發生錯誤，請稍後再試。",
        )


# ============================================================
# Bot 本體與常駐面板初始化
# ============================================================

class LineupBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        # 本機器人不讀取聊天訊息，因此不需要 Message Content Intent。
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,
        )
        self.panels_ready = False

    async def setup_hook(self) -> None:
        await database.initialize()

        # 註冊 Persistent Views，讓舊面板在重啟後仍可回應。
        self.add_view(PersistentUploadPanel())
        self.add_view(PersistentQueryPanel())

    async def on_ready(self) -> None:
        logger.info(
            "已登入：%s（ID: %s）",
            self.user,
            self.user.id if self.user else "unknown",
        )

        if self.panels_ready:
            return

        try:
            await ensure_panel(
                bot=self,
                channel_id=UPLOAD_CHANNEL_ID,
                setting_key="upload_panel_message_id",
                embed=build_upload_panel_embed(),
                view=PersistentUploadPanel(),
            )
            await ensure_panel(
                bot=self,
                channel_id=WATCH_CHANNEL_ID,
                setting_key="query_panel_message_id",
                embed=build_query_panel_embed(),
                view=PersistentQueryPanel(),
            )
            self.panels_ready = True
        except Exception:
            logger.exception("建立或更新常駐面板失敗")


def build_upload_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📤 VALORANT Lineup 上傳中心",
        description=(
            "點擊下方按鈕後，依序選擇地圖與特務，"
            "再填寫影片連結及標題。\n\n"
            "**不需要輸入任何指令。**"
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(text="支援 YouTube、Instagram、Streamable 等網址")
    return embed


def build_query_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🎯 VALORANT Lineup 資料庫",
        description=(
            "從下方選單選擇地圖或特務定位，"
            "機器人會開啟你的私人查詢面板。\n"
            "選好特務後會自動顯示符合的影片。\n\n"
            "**全程不需要輸入任何指令。**"
        ),
        color=EMBED_COLOR,
    )
    embed.set_footer(
        text="為避免多人互相干擾，查詢結果只會顯示給操作者。"
    )
    return embed


async def ensure_panel(
    *,
    bot: commands.Bot,
    channel_id: int,
    setting_key: str,
    embed: discord.Embed,
    view: discord.ui.View,
) -> None:
    if channel_id <= 0:
        raise RuntimeError(
            f"{setting_key} 對應的頻道 ID 尚未設定。"
        )

    channel = bot.get_channel(channel_id)
    if channel is None:
        channel = await bot.fetch_channel(channel_id)

    if not isinstance(channel, discord.TextChannel):
        raise TypeError(
            f"頻道 {channel_id} 不是一般文字頻道。"
        )

    saved_message_id = await database.get_setting(setting_key)
    message: discord.Message | None = None

    if saved_message_id:
        try:
            message = await channel.fetch_message(int(saved_message_id))
        except (discord.NotFound, discord.Forbidden, ValueError):
            message = None

    if message:
        await message.edit(embed=embed, view=view)
        logger.info("已更新常駐面板：%s", setting_key)
        return

    message = await channel.send(embed=embed, view=view)
    await database.set_setting(setting_key, str(message.id))
    logger.info(
        "已建立常駐面板：%s，訊息 ID=%s",
        setting_key,
        message.id,
    )


def validate_environment() -> None:
    missing: list[str] = []

    if not BOT_TOKEN:
        missing.append("DISCORD_BOT_TOKEN")
    if UPLOAD_CHANNEL_ID <= 0:
        missing.append("UPLOAD_CHANNEL_ID")
    if WATCH_CHANNEL_ID <= 0:
        missing.append("WATCH_CHANNEL_ID")

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"缺少必要環境變數：{joined}")


def main() -> None:
    validate_environment()
    bot = LineupBot()
    bot.run(BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
