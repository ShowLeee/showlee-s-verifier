import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, Select
import asyncio
import datetime
import aiohttp
import os
import json
from dotenv import load_dotenv
import traceback

# ===============================
#       НАСТРОЙКИ И JSON
# ===============================

load_dotenv()

print("🔧 Инициализация бота...")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Папка для данных
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_FILE = os.path.join(DATA_DIR, "verification_settings.json")
VERIFICATIONS_FILE = os.path.join(DATA_DIR, "verification_data.json")
COOLDOWNS_FILE = os.path.join(DATA_DIR, "cooldowns.json")

def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        print(f"⚠️ Ошибка загрузки {path}")
        return {}

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False, default=str)
    except Exception as e:
        print(f"⚠️ Ошибка сохранения {path}: {e}")

# Загружаем все данные
verification_settings = load_json(SETTINGS_FILE)
verification_data = load_json(VERIFICATIONS_FILE)
cooldown_users = {
    int(k): datetime.datetime.fromisoformat(v)
    for k, v in load_json(COOLDOWNS_FILE).items()
}
pending_verifications = {}

def save_all():
    save_json(SETTINGS_FILE, verification_settings)
    save_json(VERIFICATIONS_FILE, verification_data)
    save_json(COOLDOWNS_FILE, {str(k): v.isoformat() for k, v in cooldown_users.items()})

print("📦 Данные загружены")

# ===============================
#       МОДАЛКИ НАСТРОЕК
# ===============================

class ChannelSetupModal(Modal):
    def __init__(self):
        super().__init__(title="📊 Настройка каналов")
        self.welcome_channel = TextInput(label="ID канала приветствия", placeholder="123456789012345678", required=True)
        self.log_channel = TextInput(label="ID канала логов", placeholder="123456789012345678", required=True)
        self.add_item(self.welcome_channel)
        self.add_item(self.log_channel)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id not in verification_settings:
            verification_settings[guild_id] = {}

        verification_settings[guild_id]['welcome_channel_id'] = int(self.welcome_channel.value)
        verification_settings[guild_id]['log_channel_id'] = int(self.log_channel.value)
        save_json(SETTINGS_FILE, verification_settings)

        channel = bot.get_channel(int(self.welcome_channel.value))
        if channel:
            async for msg in channel.history(limit=10):
                if msg.author == bot.user and msg.components:
                    await msg.delete()

            embed = discord.Embed(
                title="📧 Верификация",
                description="## Как пройти верификацию\n\nПосле нажатия кнопки **\"Верифицироваться\"** бот отправит вам в личные сообщения несколько вопросов.\n\nСпасибо за верификацию!",
                color=0x5865F2
            )
            await channel.send(embed=embed, view=StartVerificationView())

        await interaction.response.send_message("✅ Каналы успешно настроены!", ephemeral=True)


class RoleSetupModal(Modal):
    def __init__(self):
        super().__init__(title="👥 Настройка ролей")
        self.temp_role = TextInput(label="ID временной роли", required=True)
        self.verified_role = TextInput(label="ID верифицированной роли", required=True)
        self.admin_role = TextInput(label="ID роли администрации (для пинга)", required=True)
        self.add_item(self.temp_role)
        self.add_item(self.verified_role)
        self.add_item(self.admin_role)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id not in verification_settings:
            verification_settings[guild_id] = {}

        verification_settings[guild_id]['temp_role_id'] = int(self.temp_role.value)
        verification_settings[guild_id]['verified_role_id'] = int(self.verified_role.value)
        verification_settings[guild_id]['admin_role_id'] = int(self.admin_role.value)
        save_json(SETTINGS_FILE, verification_settings)
        await interaction.response.send_message("✅ Роли успешно настроены!", ephemeral=True)


class QuestionsSetupModal(Modal):
    def __init__(self):
        super().__init__(title="❓ Настройка вопросов")
        self.questions = TextInput(
            label="Вопросы (через ;)",
            placeholder="Как вас зовут?;Сколько вам лет?;Откуда вы о нас узнали?",
            style=discord.TextStyle.paragraph,
            required=True,
        )
        self.add_item(self.questions)

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = str(interaction.guild_id)
        if guild_id not in verification_settings:
            verification_settings[guild_id] = {}
        questions_list = [q.strip() for q in self.questions.value.split(";") if q.strip()]
        verification_settings[guild_id]['questions'] = questions_list
        save_json(SETTINGS_FILE, verification_settings)
        await interaction.response.send_message(f"✅ Установлено {len(questions_list)} вопросов!", ephemeral=True)


# ===============================
#       ВСПОМОГАТЕЛЬНЫЕ КЛАССЫ
# ===============================

class SettingsSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📊 Настройка каналов", value="channels"),
            discord.SelectOption(label="👥 Настройка ролей", value="roles"),
            discord.SelectOption(label="❓ Настройка вопросов", value="questions"),
            discord.SelectOption(label="📋 Текущие настройки", value="status")
        ]
        super().__init__(placeholder="Выберите раздел...", options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channels":
            await interaction.response.send_modal(ChannelSetupModal())
        elif val == "roles":
            await interaction.response.send_modal(RoleSetupModal())
        elif val == "questions":
            await interaction.response.send_modal(QuestionsSetupModal())
        elif val == "status":
            await show_current_settings(interaction)


async def show_current_settings(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    settings = verification_settings.get(guild_id, {})
    embed = discord.Embed(title="📊 Текущие настройки", color=0x5865F2)

    def get_mention(obj_id, get_func):
        obj = get_func(obj_id) if obj_id else None
        return obj.mention if obj else "❌ Не настроено"

    embed.add_field(name="📊 Каналы", value=f"Приветствие: {get_mention(settings.get('welcome_channel_id'), bot.get_channel)}\nЛоги: {get_mention(settings.get('log_channel_id'), bot.get_channel)}", inline=False)
    embed.add_field(name="👥 Роли", value=f"Временная: {get_mention(settings.get('temp_role_id'), interaction.guild.get_role)}\nВерифицированная: {get_mention(settings.get('verified_role_id'), interaction.guild.get_role)}\nАдмин: {get_mention(settings.get('admin_role_id'), interaction.guild.get_role)}", inline=False)

    questions = settings.get("questions", [])
    if questions:
        embed.add_field(name="❓ Вопросы", value="\n".join([f"{i+1}. {q}" for i, q in enumerate(questions[:5])]), inline=False)
    else:
        embed.add_field(name="❓ Вопросы", value="❌ Не заданы", inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


class SettingsView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SettingsSelect())


# ===============================
#        ВЕРИФИКАЦИЯ
# ===============================

class StartVerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Верифицироваться", style=discord.ButtonStyle.primary, custom_id="verify_start")
    async def start(self, interaction: discord.Interaction, button: Button):
        guild_id = str(interaction.guild_id)
        settings = verification_settings.get(guild_id)
        if not settings:
            await interaction.response.send_message("❌ Система верификации не настроена.", ephemeral=True)
            return

        # Проверка кулдауна
        if interaction.user.id in cooldown_users:
            cd = cooldown_users[interaction.user.id]
            if datetime.datetime.now() < cd:
                delta = cd - datetime.datetime.now()
                await interaction.response.send_message(f"⏳ Повторная подача через {delta.seconds//3600}ч {delta.seconds%3600//60}м", ephemeral=True)
                return

        pending_verifications[interaction.user.id] = {
            "guild_id": guild_id,
            "answers": [],
            "current": 0,
        }

        await interaction.response.send_message("✅ Проверьте личные сообщения!", ephemeral=True)
        try:
            await interaction.user.send("🚀 Начинаем верификацию! Ответьте на вопросы:")
            await send_next_question(interaction.user)
        except discord.Forbidden:
            await interaction.followup.send("❌ Не удалось отправить ЛС! Проверьте настройки приватности.", ephemeral=True)


async def send_next_question(user: discord.User):
    data = pending_verifications.get(user.id)
    if not data:
        return
    guild_id = data["guild_id"]
    settings = verification_settings.get(guild_id)
    if not settings or not settings.get("questions"):
        return

    if data["current"] < len(settings["questions"]):
        q = settings["questions"][data["current"]]
        await user.send(f"**Вопрос {data['current'] + 1}/{len(settings['questions'])}:** {q}")
    else:
        await finish_verification(user)


async def finish_verification(user: discord.User):
    data = pending_verifications.get(user.id)
    if not data:
        return

    guild_id = data["guild_id"]
    settings = verification_settings.get(guild_id)
    guild = bot.get_guild(int(guild_id))
    member = guild.get_member(user.id)
    log_channel = bot.get_channel(settings["log_channel_id"])

    embed = discord.Embed(title=f"📋 Верификация {user}", color=0x5865F2)
    for i, a in enumerate(data["answers"]):
        embed.add_field(name=f"{i+1}. {settings['questions'][i]}", value=a or "—", inline=False)

    admin_role = guild.get_role(settings["admin_role_id"])
    view = ModerationView(user.id, guild_id)
    msg = await log_channel.send(content=f"{admin_role.mention if admin_role else '@here'} Новая заявка!", embed=embed, view=view)

    verification_data[str(user.id)] = {"guild_id": guild_id, "answers": data["answers"], "message_id": msg.id, "time": datetime.datetime.now().isoformat()}
    save_json(VERIFICATIONS_FILE, verification_data)

    await user.send("✅ Ваша заявка отправлена на проверку.")
    del pending_verifications[user.id]


class ModerationView(View):
    def __init__(self, user_id, guild_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id

    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: Button):
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        s = verification_settings.get(self.guild_id)
        if member and s:
            vrole = guild.get_role(s["verified_role_id"])
            trole = guild.get_role(s["temp_role_id"])
            if trole and trole in member.roles:
                await member.remove_roles(trole)
            if vrole:
                await member.add_roles(vrole)
            await interaction.response.send_message("✅ Принято!", ephemeral=True)
            await member.send("🎉 Вы прошли верификацию!")
        else:
            await interaction.response.send_message("❌ Ошибка!", ephemeral=True)

    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: Button):
        cooldown_users[self.user_id] = datetime.datetime.now() + datetime.timedelta(hours=24)
        save_json(COOLDOWNS_FILE, {str(k): v.isoformat() for k, v in cooldown_users.items()})
        await interaction.response.send_message("❌ Отклонено!", ephemeral=True)


# ===============================
#        КОМАНДЫ
# ===============================

@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    embed = discord.Embed(title="⚙️ Настройка системы", description="Выберите раздел ниже:", color=0x5865F2)
    await ctx.send(embed=embed, view=SettingsView())


@bot.event
async def on_message(msg):
    if msg.author.bot:
        return
    if msg.guild is None and msg.author.id in pending_verifications:
        data = pending_verifications[msg.author.id]
        guild_id = data["guild_id"]
        settings = verification_settings.get(guild_id)
        if settings:
            data["answers"].append(msg.content)
            data["current"] += 1
            await send_next_question(msg.author)
    await bot.process_commands(msg)


# ===============================
#       ФОНОВЫЕ ЗАДАЧИ
# ===============================

@tasks.loop(hours=1)
async def cleanup():
    now = datetime.datetime.now()
    expired = [uid for uid, end in cooldown_users.items() if now >= end]
    for uid in expired:
        del cooldown_users[uid]
    if expired:
        save_json(COOLDOWNS_FILE, {str(k): v.isoformat() for k, v in cooldown_users.items()})
        print(f"🧹 Убраны старые кулдауны: {expired}")


@bot.event
async def on_ready():
    print(f"✅ Бот запущен как {bot.user}")
    cleanup.start()


# ===============================
#          ЗАПУСК
# ===============================

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ Нет токена в .env!")
    exit(1)

bot.run(TOKEN)
