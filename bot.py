import asyncio
import random
import time
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8987430982:AAFSc3jGgPSvTqL4XBAJQKx9hT2LqpHAdGE"
ADMIN_IDS = {5082771401}          # <-- твой Telegram user_id (@userinfobot)
DB_PATH = "casino.db"
START_BALANCE = 1000
# ===============================================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

GAME_EMOJI = {
    "боулинг": "🎳",
    "кубик": "🎲",
    "дартс": "🎯",
    "футбол": "⚽",
    "баскетбол": "🏀",
    "подушки": "🛏️"
}

WIN_FLAVORS = [
    "💅 Няшечка просто порвала всех в клочья!",
    "🔥 Это была самая жаркая схватка!",
    "✨ Няшечка непобедима!",
    "🌟 Няшечка-чемпионка!",
    "🎀 Няшечка знала, что победит!",
    "👑 Королевская победа няшечки!",
    "🩷 Няшечка снесла всех своей милотой!",
]

JOIN_FLAVORS = [
    "💥 Схватка накаляется!",
    "💫 Вторая няшечка на ринге!",
    "🎀 Битва начинается!",
    "⚡️ Сейчас будет жарко!",
]

DESTROY_FLAVORS = [
    "💀 Мразь была уничтожена без шансов!",
    "🔥 Распотрошена до последней НЯШки!",
    "💥 Мразь разлетелась на кусочки!",
    "🩸 Ни одна НЯШка не выжила!",
    "⚰️ Мразь отправлена в мир иной!",
    "💅 Масечка даже не вспотела!",
]

# ================== ЗВАНИЯ ==================
RANKS = [
    ("кроха няшечка", 0, 0),
    ("деточка няшечка", 650, 500),
    ("подросток няшечка", 1100, 1000),
    ("немаленькая такая няшечка", 1350, 1500),
    ("няшечка-сучечка", 2000, 2000),
    ("няшечка-стервочка", 2350, 2500),
    ("няшечка-танцовщица", 3000, 3000),
    ("няшечка-богинябогатейка", 4000, 3500),
    ("НЯШКА-НЕВАЛЯШКА", 5000, 4000),
    ("СВЕРХГАЛАКТИЧЕСКАЯ ВЛАДЫКА НЯШЕК", 6000, 4500),
    ("МиСс НяШ-ВсЕлЕнНаЯ", 10000, 5000),
]

active_games = {}
active_bombs = {}
hurricane_active = False

# ================== БАЗА ДАННЫХ ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 1000,
                is_admin INTEGER DEFAULT 0,
                earned INTEGER DEFAULT 0,
                rank_index INTEGER DEFAULT 0,
                last_daily INTEGER DEFAULT 0,
                custom_title TEXT DEFAULT NULL,
                marriage_id INTEGER DEFAULT NULL,
                shield_until INTEGER DEFAULT 0
            )
        """)
        # Безопасное добавление новых колонок для старых баз
        for col, definition in [
            ("last_daily", "INTEGER DEFAULT 0"),
            ("custom_title", "TEXT DEFAULT NULL"),
            ("marriage_id", "INTEGER DEFAULT NULL"),
            ("shield_until", "INTEGER DEFAULT 0")
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bank (
                user_id INTEGER PRIMARY KEY,
                amount INTEGER DEFAULT 0,
                deposit_time INTEGER DEFAULT 0
            )
        """)
        await db.commit()

async def ensure_user(user_id: int, username: str = ""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, balance, earned, rank_index, last_daily) "
            "VALUES (?, ?, ?, 0, 0, 0)",
            (user_id, username, START_BALANCE)
        )
        await db.commit()

async def get_balance(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else 0

async def add_balance(user_id: int, delta: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO users (user_id, balance) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?",
            (user_id, delta, delta)
        )
        await db.commit()

async def get_user_info(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance, earned, rank_index, custom_title, marriage_id, shield_until FROM users WHERE user_id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            return row if row else None

async def set_user_info(user_id: int, balance: int, earned: int, rank_index: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = ?, earned = ?, rank_index = ? WHERE user_id = ?",
            (balance, earned, rank_index, user_id)
        )
        await db.commit()

async def find_user_id_by_username(username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users WHERE username = ?", (username,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None

async def add_earned(user_id: int, delta: int):
    if delta <= 0: return None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET earned = earned + ? WHERE user_id = ?", (delta, user_id))
        await db.commit()
    return await check_rank_up(user_id)

async def check_rank_up(user_id: int):
    info = await get_user_info(user_id)
    if not info: return None
    balance, earned, rank_index = info[0], info[1], info[2]
    new_rank_index = rank_index

    for i in range(len(RANKS) - 1, rank_index, -1):
        if earned >= RANKS[i][1]:
            new_rank_index = i
            break

    if new_rank_index == rank_index: return None

    total_reward = sum(RANKS[i][2] for i in range(rank_index + 1, new_rank_index + 1))
    await set_user_info(user_id, balance + total_reward, earned, new_rank_index)
    return (rank_index, new_rank_index, total_reward)

async def get_rank_name(user_id: int) -> str:
    info = await get_user_info(user_id)
    if not info: return RANKS[0][0]
    if info[3]: return info[3] # Кастомный титул
    return RANKS[info[2]][0]

# ================== КОМАНДЫ ==================
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "")
    bal = await get_balance(message.from_user.id)
    rank = await get_rank_name(message.from_user.id)
    await message.answer(
        f"🌸 Приветик, няшечка! 🌸\n\n"
        f"💖 Твой балик: {bal} НЯШ 💖\n"
        f"🎖 Твоё звание: {rank}\n\n"
        f"🎮 Игры, рулетка, слоты, кражи, свадьбы и банк ждут тебя!\n"
        f"Помощь: /help\n"
        f"Магазин: /shop"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "🎀 МОЯ ПОМОЩЬ НЯШЕЧКАМ 🎀\n\n"
        "🎮 Игра с другом: «боулинг 100» (или кубик, дартс, футбол, баскетбол, подушки, слоты, рулетка, бомба)\n"
        "🤖 Игра с ботом: /rubka\n"
        "🎁 Бонус: /daily\n"
        "🏦 Банк: /bank 1000 или /bank take\n"
        "🛒 Магазин: /shop\n"
        "🥷 Кража: /steal @username\n"
        "💍 Свадьба: /marry (ответом) или /divorce\n"
        "💖 Балик: /balance\n"
        "🏆 Топ: /top\n"
        "🎖 Звание: /rank\n"
        "💸 Перевод: /pay @username 500\n"
        "🏥 Фонд: /fund 500\n"
        "🌸 Погладить: «погладить» (ответом)\n"
        "🍑 Шлёпнуть: «шлёпнуть» (ответом)\n\n"
        "💀 Секретные: /destroy, /resetrank (только масечка)\n"
    )

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "")
    bal = await get_balance(message.from_user.id)
    rank = await get_rank_name(message.from_user.id)
    await message.reply(f"💖 Твой балик: {bal} НЯШ 💖\n🎖 Звание: {rank}")

@dp.message(Command("top"))
async def cmd_top(message: Message):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id, balance, rank_index, custom_title FROM users ORDER BY balance DESC LIMIT 10") as cur:
            rows = await cur.fetchall()

    if not rows:
        await message.reply("🥺 Пока никто не играл...")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 ТОП НЯШЕЧЕК 🏆\n"]
    for i, (uid, bal, rank_i, custom) in enumerate(rows, start=1):
        try:
            chat = await bot.get_chat(uid)
            name = chat.full_name
        except Exception:
            name = str(uid)
        prefix = medals[i - 1] if i <= 3 else f"{i}."
        rank_name = custom if custom else RANKS[rank_i][0]
        lines.append(f"{prefix} {name} — {bal} НЯШ ({rank_name})")
    await message.reply("\n".join(lines))

@dp.message(Command("rank"))
async def cmd_rank(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "")
    info = await get_user_info(message.from_user.id)
    balance, earned, rank_index = info[0], info[1], info[2]
    rank_name = await get_rank_name(message.from_user.id)

    if rank_index + 1 < len(RANKS):
        next_info = RANKS[rank_index + 1]
        need = max(0, next_info[1] - earned)
        text = f"🎖 Твоё звание: {rank_name}\n💖 Балик: {balance} НЯШ\n📊 Отыграно: {earned} НЯШ\n\n✨ До следующего звания «{next_info[0]}»: {need} НЯШ"
    else:
        text = f"🎖 Твоё звание: {rank_name}\n💖 Балик: {balance} НЯШ\n📊 Отыграно: {earned} НЯШ\n\n👑 Ты достигла максимума!"
    await message.reply(text)

@dp.message(Command("ranks"))
async def cmd_ranks(message: Message):
    lines = ["🎖 ВСЕ ЗВАНИЯ 🎖\n"]
    for name, threshold, reward in RANKS:
        lines.append(f"• {name} — от {threshold} НЯШ (награда {reward})")
    await message.reply("\n".join(lines))

@dp.message(Command("pay"))
async def cmd_pay(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "")
    parts = message.text.split()
    if len(parts) != 3: return await message.reply("💡 /pay @username 500")
    target_str, amount_str = parts[1], parts[2]
    try: amount = int(amount_str)
    except ValueError: return await message.reply("🤔 Сумма — число!")

    if amount <= 0: return await message.reply("🌸 Больше нолика!")

    if target_str.startswith("@"):
        target_id = await find_user_id_by_username(target_str[1:])
        if not target_id: return await message.reply("🥺 Нет такой няшечки. /start")
    else:
        try: target_id = int(target_str)
        except ValueError: return await message.reply("🤔 Неверный ID.")

    if target_id == message.from_user.id: return await message.reply("😅 Себе не надо, используй /fund")

    if await get_balance(message.from_user.id) < amount:
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")

    await ensure_user(target_id)
    await add_balance(message.from_user.id, -amount)
    await add_balance(target_id, amount)
    await message.reply(f"💸 Переведено {amount} НЯШ!\nТвой балик: {await get_balance(message.from_user.id)}")

@dp.message(Command("fund", "charity"))
async def cmd_fund(message: Message):
    await ensure_user(message.from_user.id, message.from_user.username or "")
    parts = message.text.split()
    if len(parts) != 2: return await message.reply("🏥 /fund 500")
    try: amount = int(parts[1])
    except ValueError: return await message.reply("🤔 Сумма — число!")

    if amount <= 0: return await message.reply("🌸 Больше нолика!")
    if await get_balance(message.from_user.id) < amount:
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")

    await add_balance(message.from_user.id, -amount)
    await message.reply(f"🏥💖 ООО «НЯШЕЧКИИНВАЛИДКИ» 💖🏥\nСпасибо за {amount} НЯШ!\nТвой балик: {await get_balance(message.from_user.id)}")

@dp.message(Command("give"))
async def cmd_give(message: Message):
    if message.from_user.id not in ADMIN_IDS: return await message.reply("🙅‍♀️ Только масечка!")
    parts = message.text.split()
    if len(parts) != 3: return await message.reply("💡 /give @username 500")
    target, amount_str = parts[1], parts[2]
    try: amount = int(amount_str)
    except ValueError: return await message.reply("🤔 Число!")

    if target.startswith("@"):
        target_id = await find_user_id_by_username(target[1:])
        if not target_id: return await message.reply("🥺 Нет в базе. /start")
    else:
        try: target_id = int(target)
        except ValueError: return await message.reply("🤔 Неверный ID.")

    await ensure_user(target_id)
    await add_balance(target_id, amount)
    await message.reply(f"💝 Начислено {amount} НЯШ! Балик: {await get_balance(target_id)}")

# ================== МАГАЗИН ==================
@dp.message(Command("shop"))
async def cmd_shop(message: Message):
    await message.reply(
        "🛒 **НЯШНЫЙ МАГАЗИН** 🛒\n\n"
        "1️⃣ `/buy title Титул` — 2000 НЯШ (сменить звание в топе)\n"
        "2️⃣ `/buy shield` — 1000 НЯШ (защита от кражи на 24ч)\n"
        "3️⃣ `/buy kiss` — 500 НЯШ (поцелуйчик в щечку)\n\n"
        "Для покупки пиши: `/buy title Королева`, `/buy shield`, `/buy kiss`",
        parse_mode="Markdown"
    )

@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    await ensure_user(message.from_user.id)
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2: return await message.reply("🛒 /shop")

    item = parts[1].lower()
    bal = await get_balance(message.from_user.id)

    if item == "kiss":
        if bal < 500: return await message.reply("😔 Не хватает на поцелуйчик (нужно 500)")
        await add_balance(message.from_user.id, -500)
        await message.reply("💋 *Чмок!* Ты купила поцелуйчик в щечку! 🥰")
    
    elif item == "shield":
        if bal < 1000: return await message.reply("😔 Не хватает на щит (нужно 1000)")
        await add_balance(message.from_user.id, -1000)
        shield_until = int(time.time()) + 86400
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET shield_until = ? WHERE user_id = ?", (shield_until, message.from_user.id))
            await db.commit()
        await message.reply("🛡️ Ты купила Няшный Щит! Тебя не украсть 24 часа.")
    
    elif item == "title":
        if bal < 2000: return await message.reply("😔 Не хватает на титул (нужно 2000)")
        if len(parts) < 3: return await message.reply("💡 /buy title ТвойТитул")
        new_title = parts[2]
        await add_balance(message.from_user.id, -2000)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET custom_title = ? WHERE user_id = ?", (new_title, message.from_user.id))
            await db.commit()
        await message.reply(f"👑 Твой новый титул: {new_title}!")
    else:
        await message.reply("🛒 Неизвестный товар. Загляни в /shop")

# ================== КРАЖА ==================
@dp.message(Command("steal", "украсть"))
async def cmd_steal(message: Message):
    await ensure_user(message.from_user.id)
    parts = message.text.split()
    if len(parts) != 2: return await message.reply("🥷 /steal @username")

    target_str = parts[1]
    target_id = None
    if target_str.startswith("@"):
        target_id = await find_user_id_by_username(target_str[1:])
        if not target_id: return await message.reply("🥺 Нет такой няшечки.")
    else:
        try: target_id = int(target_str)
        except: return await message.reply("🤔 Неверный ID.")
    
    if target_id == message.from_user.id: return await message.reply("😅 Себя красть нельзя!")

    await ensure_user(target_id)
    target_info = await get_user_info(target_id)
    thief_bal = await get_balance(message.from_user.id)
    
    if target_info[5] > int(time.time()):
        return await message.reply("🛡️ У жертвы Няшный Щит! Кража не удалась.")

    if target_info[0] < 100:
        return await message.reply("🥺 У жертвы слишком мало НЯШ для кражи.")

    steal_amount = int(target_info[0] * 0.1)
    
    if random.randint(1, 6) >= 4:
        await add_balance(target_id, -steal_amount)
        await add_balance(message.from_user.id, steal_amount)
        await message.reply(f"🥷 УСПЕХ! Ты украла {steal_amount} НЯШ у няшечки!")
    else:
        penalty = min(int(thief_bal * 0.1), 500)
        await add_balance(message.from_user.id, -penalty)
        await add_balance(target_id, penalty)
        await message.reply(f"🚨 ТЕБЯ ПОЙМАЛИ! Штраф {penalty} НЯШ в пользу жертвы.")

# ================== СВАДЬБА ==================
@dp.message(Command("marry"))
async def cmd_marry(message: Message):
    if not message.reply_to_message: return await message.reply("💍 Ответь на сообщение няшечки!")
    await ensure_user(message.from_user.id)
    target_id = message.reply_to_message.from_user.id
    
    if target_id == message.from_user.id: return await message.reply("😅 На себе жениться нельзя!")
    await ensure_user(target_id)
    
    info = await get_user_info(message.from_user.id)
    if info[4]: return await message.reply("💍 Ты уже в браке! Сначала /divorce")
    
    await message.reply(f"💍 {message.reply_to_message.from_user.full_name}, ты согласна стать парой для {message.from_user.full_name}?\nНапиши /agree или /no")

@dp.message(Command("agree"))
async def cmd_agree(message: Message):
    if not message.reply_to_message: return
    proposer_id = message.reply_to_message.from_user.id
    my_id = message.from_user.id
    
    info = await get_user_info(my_id)
    if info[4]: return await message.reply("💍 Ты уже в браке!")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET marriage_id = ? WHERE user_id = ?", (my_id, proposer_id))
        await db.execute("UPDATE users SET marriage_id = ? WHERE user_id = ?", (proposer_id, my_id))
        await db.commit()
    
    await message.reply("💖 УРА! Няшечки теперь вместе! Общий бюджет активирован.")

@dp.message(Command("no"))
async def cmd_no(message: Message):
    if message.reply_to_message:
        await message.reply("💔 Ой, няшечка отказала...")

@dp.message(Command("divorce"))
async def cmd_divorce(message: Message):
    info = await get_user_info(message.from_user.id)
    if not info[4]: return await message.reply("💔 Ты не в браке!")
    
    spouse_id = info[4]
    my_bal = await get_balance(message.from_user.id)
    spouse_bal = await get_balance(spouse_id)
    total = my_bal + spouse_bal
    half = total // 2
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET balance = ?, marriage_id = NULL WHERE user_id = ?", (half, message.from_user.id))
        await db.execute("UPDATE users SET balance = ?, marriage_id = NULL WHERE user_id = ?", (half, spouse_id))
        await db.commit()
    await message.reply("💔 Развод! Имущество разделено поровну.")

# ================== ПРИКОЛЮХИ ==================
@dp.message(F.text.lower().in_({"погладить", "гладить"}))
async def cmd_pet(message: Message):
    if not message.reply_to_message: return await message.reply("🌸 Кого гладить?")
    rank = await get_rank_name(message.reply_to_message.from_user.id)
    await message.reply(f"💖 *гладит {message.reply_to_message.from_user.full_name} ({rank}) по головке* 💖\nМур-мур! 🥰")

@dp.message(F.text.lower().in_({"шлёпнуть", "шлепнуть", "шлёп", "шлеп"}))
async def cmd_spank(message: Message):
    if not message.reply_to_message: return await message.reply("🍑 Кого шлёпать?")
    rank = await get_rank_name(message.reply_to_message.from_user.id)
    await message.reply(f"🍑 *шлёпает {message.reply_to_message.from_user.full_name} ({rank}) по попке* 🍑\nАй! 😼")

# ================== СЕКРЕТНЫЕ КОМАНДЫ ==================
@dp.message(Command("destroy"))
async def cmd_destroy(message: Message):
    if message.from_user.id not in ADMIN_IDS: return await message.reply("🙅‍♀️ Только масечка!")
    if not message.reply_to_message: return await message.reply("💀 Ответь на сообщение!")
    target = message.reply_to_message.from_user
    if target.id in ADMIN_IDS: return await message.reply("😱 Нельзя уничтожать масечек!")
    await ensure_user(target.id)
    info = await get_user_info(target.id)
    await set_user_info(target.id, 0, info[1], info[2])
    await message.reply(f"💀🔥 УНИЧТОЖИТЬ МРАЗЬ 🔥💀\nНяшечка {target.full_name} потеряла {info[0]} НЯШ!\n{random.choice(DESTROY_FLAVORS)}")

@dp.message(Command("resetrank"))
async def cmd_resetrank(message: Message):
    if message.from_user.id not in ADMIN_IDS: return await message.reply("🙅‍♀️ Только масечка!")
    if not message.reply_to_message: return await message.reply("🔄 Ответь на сообщение!")
    target = message.reply_to_message.from_user
    await ensure_user(target.id)
    info = await get_user_info(target.id)
    await set_user_info(target.id, info[0], 0, 0)
    await message.reply(f"🔄✨ СБРОС ЗВАНИЯ ✨🔄\nНяшечка {target.full_name} снова кроха-няшечка!")

# ================== МИНИ-ИГРЫ ==================
@dp.message(F.text.regexp(r"^(слоты)\s+\d+$"))
async def play_slots(message: Message):
    parts = message.text.split(); bet = int(parts[1])
    if bet <= 0: return
    await ensure_user(message.from_user.id)
    if bet > await get_balance(message.from_user.id):
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")
    await add_balance(message.from_user.id, -bet)
    symbols = ["🍒", "🍋", "💎", "🩷", "👑"]
    res = [random.choice(symbols) for _ in range(3)]
    text = f"🎰 {res[0]} | {res[1]} | {res[2]}\n\n"
    if res[0] == res[1] == res[2]:
        win = bet * 5
        await add_balance(message.from_user.id, win)
        await add_earned(message.from_user.id, win)
        await check_rank_up(message.from_user.id)
        text += f"🔥 ДЖЕКПОТ x5! Выигрыш: {win} НЯШ!"
    elif res[0] == res[1] or res[1] == res[2] or res[0] == res[2]:
        win = bet * 2
        await add_balance(message.from_user.id, win)
        await add_earned(message.from_user.id, win)
        await check_rank_up(message.from_user.id)
        text += f"✨ Два одинаковых! Выигрыш: {win} НЯШ!"
    else:
        text += f"😭 Не повезло! Потеряно: {bet} НЯШ."
    await message.reply(text)

@dp.message(F.text.regexp(r"^(рулетка)\s+\d+$"))
async def play_roulette(message: Message):
    parts = message.text.split(); bet = int(parts[1])
    if bet <= 0: return
    await ensure_user(message.from_user.id)
    if bet > await get_balance(message.from_user.id):
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")
    await add_balance(message.from_user.id, -bet)
    num = random.randint(1, 10)
    text = f"🎲 Выпало число: {num}\n\n"
    if num == 10:
        win = bet * 5
        await add_balance(message.from_user.id, win)
        await add_earned(message.from_user.id, win)
        await check_rank_up(message.from_user.id)
        text += f"👑 ДЖЕКПОТ x5! Выигрыш: {win} НЯШ!"
    elif num >= 9:
        win = bet * 2
        await add_balance(message.from_user.id, win)
        await add_earned(message.from_user.id, win)
        await check_rank_up(message.from_user.id)
        text += f"🔥 Выигрыш x2! Получено: {win} НЯШ!"
    elif num >= 6:
        await add_balance(message.from_user.id, bet)
        text += f"🤝 Возврат ставки."
    else:
        text += f"😭 Не повезло! Потеряно: {bet} НЯШ."
    await message.reply(text)

@dp.message(F.text.regexp(r"^(бомба)\s+\d+$"))
async def play_bomb(message: Message):
    parts = message.text.split(); bet = int(parts[1])
    if bet <= 0: return
    await ensure_user(message.from_user.id)
    if bet > await get_balance(message.from_user.id):
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")
    await add_balance(message.from_user.id, -bet)
    msg = await message.reply(f"💣 БОМБА НА {bet} НЯШ!\nУ тебя 5 секунд, чтобы написать «разминировать»!")
    active_bombs[msg.message_id] = {"user_id": message.from_user.id, "bet": bet, "chat_id": message.chat.id, "active": True}
    await asyncio.sleep(5)
    bomb = active_bombs.get(msg.message_id)
    if bomb and bomb["active"]:
        bomb["active"] = False
        await bot.send_message(message.chat.id, f"💥 БУМ! Потеряно: {bet} НЯШ.", reply_to_message_id=message.message_id)

@dp.message(F.text.lower().in_({"разминировать", "обезвредить"}))
async def defuse_bomb(message: Message):
    if not message.reply_to_message: return
    bomb = active_bombs.get(message.reply_to_message.message_id)
    if bomb and bomb["active"] and bomb["user_id"] == message.from_user.id:
        bomb["active"] = False
        win = bomb["bet"] * 2
        await add_balance(message.from_user.id, win)
        await add_earned(message.from_user.id, win)
        await check_rank_up(message.from_user.id)
        await message.reply(f"✂️ РАЗМИНИРОВАНО! Выигрыш: {win} НЯШ!")

# ================== БАНК И БОНУСЫ ==================
@dp.message(Command("daily"))
async def cmd_daily(message: Message):
    await ensure_user(message.from_user.id)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_daily FROM users WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
            last = row[0] if row and row[0] else 0
    now = int(time.time())
    if now - last < 86400:
        wait = 86400 - (now - last)
        return await message.reply(f"⏳ Жди {wait // 3600} ч. {(wait % 3600) // 60} мин.")
    reward = random.randint(100, 500)
    await add_balance(message.from_user.id, reward)
    await add_earned(message.from_user.id, reward)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (now, message.from_user.id))
        await db.commit()
    await message.reply(f"🎁 СУНДУК ОТКРЫТ! Внутри: {reward} НЯШ 💖")

@dp.message(Command("bank"))
async def cmd_bank(message: Message):
    await ensure_user(message.from_user.id)
    parts = message.text.split()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT amount, deposit_time FROM bank WHERE user_id = ?", (message.from_user.id,)) as cur:
            row = await cur.fetchone()
            bank_amt, dep_time = (row[0], row[1]) if row else (0, 0)
    now = int(time.time())
    if len(parts) == 2 and parts[1].lower() in ["take", "забрать"]:
        if bank_amt <= 0: return await message.reply("🏦 Нет вклада!")
        if now - dep_time < 86400:
            withdraw = bank_amt - int(bank_amt * 0.10)
            text = f"🏦 Забрала раньше! Штраф 10%. Получено: {withdraw} НЯШ."
        else:
            withdraw = int(bank_amt * 1.10)
            text = f"🏦 Вклад созрел! Получено: {withdraw} НЯШ (x1.10)."
        await add_balance(message.from_user.id, withdraw)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM bank WHERE user_id = ?", (message.from_user.id,))
            await db.commit()
        return await message.reply(text)
    if len(parts) != 2: return await message.reply("🏦 /bank 1000 или /bank take")
    try: amount = int(parts[1])
    except: return await message.reply("🤔 Число!")
    if amount <= 0: return await message.reply("🌸 Больше нолика!")
    if bank_amt > 0: return await message.reply("🏦 Уже есть вклад! /bank take")
    if await get_balance(message.from_user.id) < amount: return await message.reply("😔 Не хватает!")
    await add_balance(message.from_user.id, -amount)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO bank VALUES (?, ?, ?)", (message.from_user.id, amount, now))
        await db.commit()
    await message.reply(f"🏦 Ты положила {amount} НЯШ под 10%!")

# ================== УРАГАН ==================
async def hurricane_loop():
    global hurricane_active
    while True:
        await asyncio.sleep(7200) # Раз в 2 часа
        # В реальности тут нужно получить ID чата, но для простоты бот кинет в последний активный (если есть)
        # Или можно вручную вызывать через админку
        pass

# ================== РУБКА С БОТОМ ==================
@dp.message(Command("rubka"))
async def cmd_rubka(message: Message):
    await ensure_user(message.from_user.id)
    await message.answer(
        "🤖 **РУБКА С БОТОМ** 🤖\n\n"
        "Напиши: `рубка кубик 100` (или боулинг, дартс, футбол, баскетбол, слоты)\n"
        "Вместо 100 пиши свою ставку!",
        parse_mode="Markdown"
    )

@dp.message(F.text.regexp(r"^рубка\s+(боулинг|кубик|дартс|футбол|баскетбол|слоты)\s+\d+$"))
async def start_bot_game(message: Message):
    parts = message.text.split()
    game_name, bet = parts[1], int(parts[2])
    if bet <= 0: return
    await ensure_user(message.from_user.id)
    if bet > await get_balance(message.from_user.id):
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")

    emoji = GAME_EMOJI.get(game_name, "🎲")
    await add_balance(message.from_user.id, -bet)
    player_dice = await message.bot.send_dice(chat_id=message.chat.id, emoji=emoji, reply_to_message_id=message.message_id)
    await asyncio.sleep(1.5)
    bot_dice = await message.bot.send_dice(chat_id=message.chat.id, emoji=emoji)
    
    p_val, b_val = player_dice.dice.value, bot_dice.dice.value
    pot = bet * 2
    text = f"🤖 РУБКА\nТы: {p_val}\nБот: {b_val}\n\n"
    
    if p_val > b_val:
        await add_balance(message.from_user.id, pot)
        await add_earned(message.from_user.id, pot)
        await check_rank_up(message.from_user.id)
        text += f"🏆 ПОБЕДА! Выигрыш: {pot} НЯШ"
    elif p_val < b_val:
        text += f"😭 БОТ ПОБЕДИЛ! Потеряно: {bet} НЯШ"
    else:
        await add_balance(message.from_user.id, bet)
        text += f"🤝 НИЧЬЯ! Возврат {bet} НЯШ"
    await message.answer(text)

# ================== ДУЭЛИ ==================
@dp.message(F.text.regexp(r"^(боулинг|кубик|дартс|футбол|баскетбол|подушки)\s+\d+$"))
async def start_game(message: Message):
    parts = message.text.split()
    game_name, bet = parts[0], int(parts[1])
    if bet <= 0: return
    await ensure_user(message.from_user.id)
    if bet > await get_balance(message.from_user.id):
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")

    emoji = GAME_EMOJI[game_name]
    await add_balance(message.from_user.id, -bet)
    sent = await message.bot.send_dice(chat_id=message.chat.id, emoji=emoji, reply_to_message_id=message.message_id)
    
    active_games[sent.message_id] = {
        "chat_id": message.chat.id, "creator": message.from_user.id,
        "bet": bet, "emoji": emoji, "game_name": game_name,
        "players": {message.from_user.id: sent.dice.value}
    }
    await message.answer(f"🩷🤯ПРОТИВОСТОЯНИЕ НЯШЕЧЕК🤯🩷\nИгрулька: {game_name}\nСтавка: {bet} НЯШ\nУ создателя: {sent.dice.value}\n👉 Ответь эмодзи {emoji}!")

@dp.message(F.reply_to_message, F.dice)
async def join_game(message: Message):
    game = active_games.get(message.reply_to_message.message_id)
    if not game or message.dice.emoji != game["emoji"]: return
    user_id = message.from_user.id
    if user_id in game["players"]: return await message.reply("😾Ты уже сражаешься!")
    if len(game["players"]) >= 2: return await message.reply("няяш, тут уже играют !")
    await ensure_user(user_id)
    if await get_balance(user_id) < game["bet"]:
        return await message.reply("😔няяшечка😔 савсемушки не осталось 💵денюжек💵")
    
    await add_balance(user_id, -game["bet"])
    game["players"][user_id] = message.dice.value
    await message.reply(f"😻НЯШЕЧКА ХОЧЕТ СРАЗИТЬСЯ😻\nТвой результат: {message.dice.value}")
    
    if len(game["players"]) >= 2:
        await finalize_game(message.reply_to_message.message_id)

async def finalize_game(game_id: int):
    game = active_games.pop(game_id, None)
    if not game: return
    players = game["players"]
    max_val = max(players.values())
    winners = [uid for uid, v in players.items() if v == max_val]
    pot = game["bet"] * len(players)
    
    if len(winners) == 1:
        winner_id = winners[0]
        await add_balance(winner_id, pot)
        await add_earned(winner_id, pot)
        await check_rank_up(winner_id)
        new_bal = await get_balance(winner_id)
        try: name = (await bot.get_chat(winner_id)).full_name
        except: name = str(winner_id)
        text = f"🤯СРАЗИЛИСЬ В СХВАТКЕ🤯\nВЫИГРАЛА: {name}\nРезультат: {max_val}\nВыигрыш: {pot} НЯШ\nНовый балик: {new_bal}\n\n{random.choice(WIN_FLAVORS)}"
        await bot.send_message(game["chat_id"], text)
    else:
        for uid in players: await add_balance(uid, game["bet"])
        await bot.send_message(game["chat_id"], "🥰НИЧЬЯШЕЧКА🥰 ВАШИ 💸ДЕНЮЖКИ ВОЗВРАЩЕНЫ💸")

# ================== ЗАПУСК ==================
from aiohttp import web

async def web_server():
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text="Bot is alive!"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

async def main():
    await init_db()
    asyncio.create_task(web_server()) # Запускаем мини-сайт
    print("Бот-няшечка запущен... 🌸")
    await dp.start_polling(bot)
