import discord
from discord.ext import commands, tasks
from discord.ui import Button, View, Modal, TextInput, Select
import asyncio
import datetime
import aiohttp
import os
from dotenv import load_dotenv
import traceback

# Загружаем переменные окружения
load_dotenv()

print("🔧 Инициализация бота...")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище данных
verification_data = {}
pending_verifications = {}
verification_settings = {}
cooldown_users = {}  # {user_id: cooldown_end_time}

print("📦 Загрузка модулей завершена")

class ChannelSetupModal(Modal):
    def __init__(self):
        super().__init__(title="📊 Настройка каналов")
        
        self.welcome_channel = TextInput(
            label="ID канала приветствия",
            placeholder="123456789012345678",
            style=discord.TextStyle.short,
            required=True,
            max_length=20
        )
        
        self.log_channel = TextInput(
            label="ID канала логов",
            placeholder="123456789012345678",
            style=discord.TextStyle.short,
            required=True,
            max_length=20
        )
        
        self.add_item(self.welcome_channel)
        self.add_item(self.log_channel)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print(f"📝 Настройка каналов для сервера {interaction.guild_id}")
            guild_id = interaction.guild_id
            
            if guild_id not in verification_settings:
                verification_settings[guild_id] = {}
            
            verification_settings[guild_id]['welcome_channel_id'] = int(self.welcome_channel.value)
            verification_settings[guild_id]['log_channel_id'] = int(self.log_channel.value)
            
            # Создаем/обновляем сообщение верификации
            channel = bot.get_channel(int(self.welcome_channel.value))
            if channel:
                # Удаляем старые сообщения бота
                async for message in channel.history(limit=10):
                    if message.author == bot.user and message.components:
                        await message.delete()
                
                embed = discord.Embed(
                    title="📧 Верификация",
                    description="## Как пройти верификацию\n\nПосле нажатия кнопки **\"Верифицироваться\"** бот отправит вам в личные сообщения несколько вопросов. Вы должны заполнить всю форму для доступа к серверу.\n\nНажмите кнопку **\"Верифицироваться\"** ниже чтобы начать верификацию\n\nСпасибо за верификацию!",
                    color=0x5865F2
                )
                
                view = StartVerificationView()
                await channel.send(embed=embed, view=view)
                
            await interaction.response.send_message("✅ Каналы успешно настроены!", ephemeral=True)
            print(f"✅ Каналы настроены для сервера {interaction.guild_id}")
            
        except Exception as e:
            print(f"❌ Ошибка в настройке каналов: {e}")
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

class RoleSetupModal(Modal):
    def __init__(self):
        super().__init__(title="👥 Настройка ролей")
        
        self.temp_role = TextInput(
            label="ID временной роли",
            placeholder="123456789012345678",
            style=discord.TextStyle.short,
            required=True,
            max_length=20
        )
        
        self.verified_role = TextInput(
            label="ID верифицированной роли",
            placeholder="123456789012345678",
            style=discord.TextStyle.short,
            required=True,
            max_length=20
        )
        
        self.admin_role = TextInput(
            label="ID роли администрации (для пинга)",
            placeholder="123456789012345678",
            style=discord.TextStyle.short,
            required=True,
            max_length=20
        )
        
        self.add_item(self.temp_role)
        self.add_item(self.verified_role)
        self.add_item(self.admin_role)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print(f"👥 Настройка ролей для сервера {interaction.guild_id}")
            guild_id = interaction.guild_id
            
            if guild_id not in verification_settings:
                verification_settings[guild_id] = {}
            
            verification_settings[guild_id]['temp_role_id'] = int(self.temp_role.value)
            verification_settings[guild_id]['verified_role_id'] = int(self.verified_role.value)
            verification_settings[guild_id]['admin_role_id'] = int(self.admin_role.value)
            
            await interaction.response.send_message("✅ Роли успешно настроены!", ephemeral=True)
            print(f"✅ Роли настроены для сервера {interaction.guild_id}")
            
        except Exception as e:
            print(f"❌ Ошибка в настройке ролей: {e}")
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

class QuestionsSetupModal(Modal):
    def __init__(self):
        super().__init__(title="❓ Настройка вопросов")
        
        self.questions = TextInput(
            label="Вопросы (через ;)",
            placeholder="Как вас зовут?;Сколько вам лет?;Откуда вы о нас узнали?",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        
        self.add_item(self.questions)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            print(f"❓ Настройка вопросов для сервера {interaction.guild_id}")
            guild_id = interaction.guild_id
            
            if guild_id not in verification_settings:
                verification_settings[guild_id] = {}
            
            questions_list = [q.strip() for q in self.questions.value.split(';') if q.strip()]
            verification_settings[guild_id]['questions'] = questions_list
            
            await interaction.response.send_message(f"✅ Установлено {len(questions_list)} вопросов!", ephemeral=True)
            print(f"✅ Вопросы настроены для сервера {interaction.guild_id}")
            
        except Exception as e:
            print(f"❌ Ошибка в настройке вопросов: {e}")
            await interaction.response.send_message(f"❌ Ошибка: {e}", ephemeral=True)

class SettingsSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="📊 Настройка каналов",
                description="Настройка каналов для верификации",
                value="channels"
            ),
            discord.SelectOption(
                label="👥 Настройка ролей", 
                description="Настройка ролей для верификации",
                value="roles"
            ),
            discord.SelectOption(
                label="❓ Настройка вопросов",
                description="Настройка вопросов для верификации", 
                value="questions"
            ),
            discord.SelectOption(
                label="📋 Текущие настройки",
                description="Просмотр текущих настроек",
                value="status"
            )
        ]
        super().__init__(placeholder="Выберите нужный раздел...", options=options)

    async def callback(self, interaction: discord.Interaction):
        print(f"🎯 Выбрана настройка: {self.values[0]} для сервера {interaction.guild_id}")
        if self.values[0] == "channels":
            modal = ChannelSetupModal()
            await interaction.response.send_modal(modal)
            
        elif self.values[0] == "roles":
            modal = RoleSetupModal()
            await interaction.response.send_modal(modal)
            
        elif self.values[0] == "questions":
            modal = QuestionsSetupModal()
            await interaction.response.send_modal(modal)
            
        elif self.values[0] == "status":
            await show_current_settings(interaction)

async def show_current_settings(interaction: discord.Interaction):
    print(f"📊 Просмотр настроек для сервера {interaction.guild_id}")
    guild_id = interaction.guild_id
    settings = verification_settings.get(guild_id, {})
    
    embed = discord.Embed(
        title="📊 Текущие настройки верификации",
        color=0x5865F2,
        timestamp=datetime.datetime.now()
    )
    
    # Каналы
    welcome_channel = bot.get_channel(settings.get('welcome_channel_id', 0))
    log_channel = bot.get_channel(settings.get('log_channel_id', 0))
    
    embed.add_field(
        name="📊 Каналы",
        value=f"**Приветствие:** {welcome_channel.mention if welcome_channel else '❌ Не настроен'}\n"
              f"**Логи:** {log_channel.mention if log_channel else '❌ Не настроен'}",
        inline=False
    )
    
    # Роли
    temp_role = interaction.guild.get_role(settings.get('temp_role_id', 0))
    verified_role = interaction.guild.get_role(settings.get('verified_role_id', 0))
    admin_role = interaction.guild.get_role(settings.get('admin_role_id', 0))
    
    embed.add_field(
        name="👥 Роли", 
        value=f"**Временная:** {temp_role.mention if temp_role else '❌ Не настроена'}\n"
              f"**Верифицированная:** {verified_role.mention if verified_role else '❌ Не настроена'}\n"
              f"**Администрации:** {admin_role.mention if admin_role else '❌ Не настроена'}",
        inline=False
    )
    
    # Вопросы
    questions = settings.get('questions', [])
    embed.add_field(
        name="❓ Вопросы",
        value=f"**Количество:** {len(questions)}\n" + 
              ("\n".join([f"{i+1}. {q}" for i, q in enumerate(questions[:3])]) + 
              ("\n..." if len(questions) > 3 else "") if questions else "❌ Не настроены"),
        inline=False
    )
    
    # Статус системы
    all_configured = all([
        settings.get('welcome_channel_id'),
        settings.get('log_channel_id'), 
        settings.get('temp_role_id'),
        settings.get('verified_role_id'),
        settings.get('admin_role_id'),
        settings.get('questions')
    ])
    
    status = "✅ **Система готова к работе!**" if all_configured else "⚠️ **Система не полностью настроена**"
    embed.add_field(name="🔧 Статус системы", value=status, inline=False)
    
    embed.set_footer(text=f"Запрос от {interaction.user.display_name}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

class SettingsView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(SettingsSelect())

class DenyReasonModal(Modal):
    def __init__(self, user_id: int):
        super().__init__(title="Отклонение с причиной")
        self.user_id = user_id
        
        self.reason = TextInput(
            label="Причина отклонения",
            placeholder="Опишите причину отклонения верификации...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        print(f"❌ Отклонение верификации пользователя {self.user_id} с причиной")
        await handle_verification_deny(interaction, self.user_id, self.reason.value)

async def handle_verification_deny(interaction: discord.Interaction, user_id: int, reason: str = None):
    """Обработка отклонения верификации"""
    print(f"🚫 Обработка отклонения верификации для пользователя {user_id}")
    user = bot.get_user(user_id)
    
    # Устанавливаем кулдаун на 24 часа
    cooldown_users[user_id] = datetime.datetime.now() + datetime.timedelta(hours=24)
    
    # Отправляем сообщение пользователю
    if user:
        try:
            if reason:
                await user.send(f"❌ **Ваша верификация отклонена.**\n**Причина:** {reason}\n\nВы сможете повторно подать заявку через 24 часа.")
            else:
                await user.send("❌ **Ваша верификация отклонена.**\n\nВы сможете повторно подать заявку через 24 часа.")
            print(f"📨 Уведомление отправлено пользователю {user_id}")
        except discord.Forbidden:
            print(f"⚠️ Не удалось отправить уведомление пользователю {user_id}")
            pass
    
    # Обновляем сообщение в канале логов
    embed = interaction.message.embeds[0]
    embed.color = 0xff0000
    embed.title = f"❌ {user.display_name if user else 'Пользователь'} (ОТКЛОНЕНО)"
    
    status_text = f"Отклонено {interaction.user.mention}\n<t:{int(datetime.datetime.now().timestamp())}:F>"
    if reason:
        status_text += f"\n**Причина:** {reason}"
    
    # Ищем поле статуса или добавляем новое
    found_status = False
    for i, field in enumerate(embed.fields):
        if field.name == "Статус":
            embed.set_field_at(i, name="Статус", value=status_text, inline=False)
            found_status = True
            break
    
    if not found_status:
        embed.add_field(name="Статус", value=status_text, inline=False)
    
    await interaction.message.edit(embed=embed, view=None)
    await interaction.response.send_message("✅ Верификация отклонена!", ephemeral=True)
    print(f"✅ Верификация пользователя {user_id} отклонена")

class StartVerificationView(View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Верифицироваться", style=discord.ButtonStyle.primary, custom_id="verify_start")
    async def verify_button(self, interaction: discord.Interaction, button: Button):
        print(f"🔐 Начало верификации пользователя {interaction.user.id}")
        settings = verification_settings.get(interaction.guild_id)
        if not settings:
            print(f"❌ Система верификации не настроена для сервера {interaction.guild_id}")
            await interaction.response.send_message("❌ Система верификации не настроена.", ephemeral=True)
            return
        
        # Проверяем кулдаун
        if interaction.user.id in cooldown_users:
            cooldown_end = cooldown_users[interaction.user.id]
            if datetime.datetime.now() < cooldown_end:
                time_left = cooldown_end - datetime.datetime.now()
                hours_left = int(time_left.total_seconds() // 3600)
                minutes_left = int((time_left.total_seconds() % 3600) // 60)
                print(f"⏰ Пользователь {interaction.user.id} на кулдауне")
                await interaction.response.send_message(
                    f"❌ Вы можете повторно подать заявку через {hours_left}ч {minutes_left}м", 
                    ephemeral=True
                )
                return
        
        # Проверяем, не проходит ли пользователь уже верификацию
        if interaction.user.id in pending_verifications:
            print(f"⚠️ Пользователь {interaction.user.id} уже проходит верификацию")
            await interaction.response.send_message("❌ Вы уже проходите верификацию!", ephemeral=True)
            return
        
        # Начинаем верификацию в ЛС
        try:
            await interaction.user.send("🚀 **Начинаем процесс верификации!** Ответьте на следующие вопросы:")
            
            # Инициализируем данные верификации
            pending_verifications[interaction.user.id] = {
                'guild_id': interaction.guild_id,
                'answers': [],
                'current_question': 0,
                'total_questions': len(settings['questions'])
            }
            
            # Немедленно отправляем первый вопрос
            await send_next_question(interaction.user)
            await interaction.response.send_message("✅ Проверьте ваши личные сообщения!", ephemeral=True)
            print(f"✅ Верификация начата для пользователя {interaction.user.id}")
            
        except discord.Forbidden:
            print(f"❌ Не удалось отправить ЛС пользователю {interaction.user.id}")
            await interaction.response.send_message("❌ Не могу отправить вам сообщение! Проверьте настройки приватности.", ephemeral=True)

async def send_next_question(user: discord.User):
    if user.id not in pending_verifications:
        print(f"⚠️ Пользователь {user.id} не найден в pending_verifications")
        return
    
    data = pending_verifications[user.id]
    settings = verification_settings.get(data['guild_id'])
    
    if not settings or not settings['questions']:
        print(f"❌ Нет настроек или вопросов для пользователя {user.id}")
        return
    
    current_index = data['current_question']
    
    # Проверяем, есть ли еще вопросы
    if current_index < len(settings['questions']):
        question = settings['questions'][current_index]
        
        # Отправляем вопрос
        await user.send(f"**📝 Вопрос {current_index + 1}/{data['total_questions']}:**\n{question}")
        print(f"📝 Отправлен вопрос {current_index + 1} пользователю {user.id}")
        
    else:
        # Все вопросы отвечены - завершаем верификацию
        print(f"✅ Все вопросы отвечены пользователем {user.id}")
        await finish_verification(user)

async def finish_verification(user: discord.User):
    print(f"🏁 Завершение верификации пользователя {user.id}")
    if user.id not in pending_verifications:
        print(f"⚠️ Пользователь {user.id} не найден в pending_verifications")
        return
    
    data = pending_verifications[user.id]
    settings = verification_settings.get(data['guild_id'])
    
    if not settings:
        print(f"❌ Нет настроек для сервера {data['guild_id']}")
        return
    
    # Создаем embed с заявкой
    guild = bot.get_guild(data['guild_id'])
    member = guild.get_member(user.id)
    
    embed = discord.Embed(
        title=f"📋 Верификация {user.display_name}",
        color=0x5865F2,
        timestamp=datetime.datetime.now()
    )
    
    # Информация о пользователе
    embed.add_field(
        name="👤 Информация о пользователе",
        value=f"**Имя пользователя:** {user}\n"
              f"**ID пользователя:** {user.id}\n"
              f"**Аккаунт создан:** <t:{int(user.created_at.timestamp())}:R>\n"
              f"**Присоединился к серверу:** <t:{int(member.joined_at.timestamp())}:R>",
        inline=False
    )
    
    # Ответы на вопросы
    for i, answer in enumerate(data['answers']):
        if i < len(settings['questions']):
            embed.add_field(
                name=f"{i + 1}. {settings['questions'][i]}",
                value=answer or "*Нет ответа*",
                inline=False
            )
    
    embed.set_footer(text=f"ID: {user.id}")
    
    # Отправляем в канал логов с пингом администрации
    log_channel = bot.get_channel(settings['log_channel_id'])
    if log_channel:
        admin_role = guild.get_role(settings['admin_role_id'])
        ping_text = admin_role.mention if admin_role else "@everyone"
        
        view = ModerationView(user.id, data['guild_id'])
        message = await log_channel.send(
            content=f"{ping_text} Новая заявка на верификацию!",
            embed=embed, 
            view=view
        )
        
        # Сохраняем данные
        verification_data[user.id] = {
            'message_id': message.id,
            'guild_id': data['guild_id'],
            'answers': data['answers'],
            'timestamp': datetime.datetime.now()
        }
        print(f"📨 Заявка отправлена в канал логов для пользователя {user.id}")
    
    # Уведомляем пользователя
    await user.send("✅ **Ваша заявка отправлена на модерацию!** Ожидайте решения.")
    
    # Очищаем временные данные
    del pending_verifications[user.id]
    print(f"✅ Верификация завершена для пользователя {user.id}")

class ModerationView(View):
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, custom_id="verify_accept")
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        print(f"✅ Принятие верификации пользователя {self.user_id}")
        settings = verification_settings.get(self.guild_id)
        if not settings:
            await interaction.response.send_message("❌ Настройки не найдены!", ephemeral=True)
            return
        
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        
        if member:
            # Меняем роли
            temp_role = guild.get_role(settings['temp_role_id'])
            verified_role = guild.get_role(settings['verified_role_id'])
            
            if temp_role and temp_role in member.roles:
                await member.remove_roles(temp_role)
            if verified_role:
                await member.add_roles(verified_role)
            
            # Обновляем embed
            embed = interaction.message.embeds[0]
            embed.color = 0x00ff00
            embed.title = f"✅ {member.display_name} (ВЕРИФИЦИРОВАН)"
            
            status_text = f"Верифицирован {interaction.user.mention}\n<t:{int(datetime.datetime.now().timestamp())}:F>"
            
            # Ищем поле статуса или добавляем новое
            found_status = False
            for i, field in enumerate(embed.fields):
                if field.name == "Статус":
                    embed.set_field_at(i, name="Статус", value=status_text, inline=False)
                    found_status = True
                    break
            
            if not found_status:
                embed.add_field(name="Статус", value=status_text, inline=False)
            
            await interaction.message.edit(embed=embed, view=None)
            
            # Уведомляем пользователя
            try:
                await member.send("🎉 **Ваша верификация одобрена!** Добро пожаловать на сервер!")
            except:
                pass
            
            await interaction.response.send_message("✅ Пользователь верифицирован!", ephemeral=True)
            print(f"🎉 Пользователь {self.user_id} верифицирован")
        else:
            await interaction.response.send_message("❌ Пользователь не найден на сервере!", ephemeral=True)
    
    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, custom_id="verify_deny")
    async def deny_button(self, interaction: discord.Interaction, button: Button):
        print(f"❌ Отклонение верификации пользователя {self.user_id}")
        await handle_verification_deny(interaction, self.user_id)
    
    @discord.ui.button(label="Отклонить с причиной", style=discord.ButtonStyle.secondary, custom_id="verify_deny_reason")
    async def deny_reason_button(self, interaction: discord.Interaction, button: Button):
        print(f"📝 Отклонение с причиной пользователя {self.user_id}")
        modal = DenyReasonModal(self.user_id)
        await interaction.response.send_modal(modal)
    
    
    @discord.ui.button(label="Кикнуть", style=discord.ButtonStyle.danger, custom_id="verify_kick")
    async def kick_button(self, interaction: discord.Interaction, button: Button):
        print(f"👢 Кик пользователя {self.user_id}")
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        
        if member:
            try:
                # Кикаем пользователя
                await member.kick(reason="Верификация отклонена")
                
                # Обрабатываем отклонение верификации
                await handle_verification_deny(interaction, self.user_id, "Пользователь был кикнут с сервера")
                print(f"✅ Пользователь {self.user_id} кикнут")
                
            except discord.Forbidden:
                await interaction.response.send_message("❌ Недостаточно прав для кика пользователя!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Пользователь не найден!", ephemeral=True)

# Команды бота
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Настройка системы верификации"""
    print(f"⚙️ Запуск настройки сервера {ctx.guild.id}")
    embed = discord.Embed(
        title="⚙️ Настройка модулей бота",
        description="Взаимодействуйте с выпадающим меню выбора, чтобы настроить систему верификации.",
        color=0x5865F2,
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(
        name="📊 Доступные настройки:",
        value="• **Каналы** - настройка каналов для верификации\n"
              "• **Роли** - настройка ролей для системы\n"
              "• **Вопросы** - настройка вопросов для верификации\n"
              "• **Статус** - просмотр текущих настроек",
        inline=False
    )
    
    embed.set_footer(text=f"Запрос от {ctx.author.display_name}")
    
    view = SettingsView()
    await ctx.send(embed=embed, view=view)

@bot.event
async def on_message(message):
    # Игнорируем сообщения от ботов
    if message.author.bot:
        return
        
    # Обработка ответов в ЛС
    if message.guild is None and message.author.id in pending_verifications:
        print(f"💬 Получен ответ от пользователя {message.author.id}")
        data = pending_verifications[message.author.id]
        settings = verification_settings.get(data['guild_id'])
        
        if settings and data['current_question'] < len(settings['questions']):
            # Сохраняем ответ
            pending_verifications[message.author.id]['answers'].append(message.content)
            pending_verifications[message.author.id]['current_question'] += 1
            
            # Отправляем следующий вопрос
            await send_next_question(message.author)
    
    await bot.process_commands(message)

@tasks.loop(hours=1)
async def cleanup_cooldowns():
    """Очистка устаревших кулдаунов"""
    current_time = datetime.datetime.now()
    expired_users = [
        user_id for user_id, cooldown_end in cooldown_users.items() 
        if current_time >= cooldown_end
    ]
    
    for user_id in expired_users:
        del cooldown_users[user_id]
        print(f"🧹 Очищен кулдаун для пользователя {user_id}")

# События бота
@bot.event
async def on_connect():
    print('🔗 Бот подключился к Discord')

@bot.event
async def on_disconnect():
    print('🔌 Бот отключился от Discord')

@bot.event
async def on_ready():
    print('=' * 50)
    print(f'✅ БОТ УСПЕШНО ЗАПУЩЕН!')
    print(f'🤖 Имя: {bot.user.name}')
    print(f'🆔 ID: {bot.user.id}')
    print(f'📊 Серверов: {len(bot.guilds)}')
    print(f'👥 Пользователей: {sum(g.member_count for g in bot.guilds)}')
    print(f'📅 Время: {datetime.datetime.now()}')
    print('=' * 50)
    
    # Запускаем фоновые задачи
    cleanup_cooldowns.start()
    print('🔄 Фоновые задачи запущены')

@bot.event
async def on_command_error(ctx, error):
    print(f'❌ Ошибка команды: {error}')
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Команда не найдена!")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ У вас недостаточно прав для выполнения этой команды!")
    else:
        await ctx.send(f"❌ Произошла ошибка: {error}")

@bot.event
async def on_error(event, *args, **kwargs):
    print(f'❌ Ошибка в событии {event}:')
    traceback.print_exc()

# Запуск бота
print("🚀 Запуск бота...")
print(f"📁 Токен из .env: {'✅ Найден' if os.getenv('DISCORD_TOKEN') else '❌ Не найден'}")

try:
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ ТОКЕН НЕ НАЙДЕН В .env ФАЙЛЕ!")
        print("📝 Убедитесь, что файл .env существует и содержит DISCORD_TOKEN=ваш_токен")
        input("Нажмите Enter для выхода...")
        exit(1)
    
    print("🔐 Попытка подключения к Discord...")
    bot.run(TOKEN)
    
except discord.LoginFailure:
    print("❌ НЕВЕРНЫЙ ТОКЕН БОТА!")
    print("📝 Проверьте токен в .env файле")
    input("Нажмите Enter для выхода...")
    
except discord.HTTPException as e:
    print(f"❌ ОШИБКА ПОДКЛЮЧЕНИЯ: {e}")
    input("Нажмите Enter для выхода...")
    
except Exception as e:
    print(f"❌ НЕИЗВЕСТНАЯ ОШИБКА: {e}")
    traceback.print_exc()
    input("Нажмите Enter для выхода...")