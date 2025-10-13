# advanced_cricket_bot.py
import telebot
from telebot import types
import requests
import random
import sqlite3
import threading
import time
import traceback

# ================== CONFIG ==================
# ================== CONFIG ==================
TELEGRAM_TOKEN = "7833033071:AAH-3RtBLk6JCV66JKHmPLalAErgAsFuv0g"
CRICKET_API_KEY  = "va5IlHSAJTNy7o368jHuS2SYUbXSGMPFtbMzED9SDtnoTd0b3rNhAI42IF2s"
WEATHER_API_KEY  = "b6907d289e10d714a6e88b30761fae22"
POLL_INTERVAL    = 30   # seconds between polling the cricket API for updates
DATABASE_FILE    = "bot_data.sqlite"
# =======================
# ============================================

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ========== Simple SQLite DB helpers ==========
def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    # users table (store chat_id and name)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER PRIMARY KEY,
                    name TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    # subscriptions: chat subscribes to match_id
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    match_id TEXT,
                    match_title TEXT,
                    last_score TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    conn.commit()
    conn.close()

def add_user(chat_id, name):"6719586667"
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (chat_id, name) VALUES (?,?)', (chat_id, name))
    conn.commit()
    conn.close()

def add_subscription(chat_id, match_id, match_title):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('INSERT INTO subscriptions (chat_id, match_id, match_title, last_score) VALUES (?,?,?,?)',
              (chat_id, match_id, match_title, ""))
    conn.commit()
    conn.close()

def remove_subscription(chat_id, match_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('DELETE FROM subscriptions WHERE chat_id=? AND match_id=?', (chat_id, match_id))
    conn.commit()
    conn.close()

def get_subscriptions_for_match(match_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('SELECT chat_id, last_score FROM subscriptions WHERE match_id=?', (match_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def update_last_score(chat_id, match_id, new_score):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('UPDATE subscriptions SET last_score=? WHERE chat_id=? AND match_id=?', (new_score, chat_id, match_id))
    conn.commit()
    conn.close()

def get_user_subscriptions(chat_id):
    conn = sqlite3.connect(DATABASE_FILE)
    c = conn.cursor()
    c.execute('SELECT match_id, match_title FROM subscriptions WHERE chat_id=?', (chat_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# ========== Cricket API helpers ==========
def fetch_current_matches():va5IlHSAJTNy7o368jHuS2SYUbXSGMPFtbMzED9SDtnoTd0b3rNhAI42IF2s
    """
    Tries to fetch current matches from common cricket APIs.
    Returns list of matches (dict) or None.
    Each match dict should contain at least: id (string), title (string), score (string), status (string)
    """
    results = []
    # 1) Try CricAPI v1 currentMatches endpoint (example)
    try:
        url = f"https://api.cricapi.com/v1/currentMatches?apikey={CRICKET_API_KEY}&offset=0"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            j = r.json()
            data = j.get("data") or j.get("matches") or j.get("response") or j.get("result") or []
            # data is likely a list of matches
            for m in data:
                # try multiple possible keys
                mid = str(m.get("id") or m.get("unique_id") or m.get("uniqueId") or m.get("matchId") or "")
                title = m.get("name") or m.get("match_title") or m.get("title") or m.get("team-1","") + " v " + m.get("team-2","")
                # score and status fields may differ
                score = m.get("score") or m.get("score_str") or m.get("scorecard") or m.get("match_score") or ""
                status = m.get("status") or m.get("matchStarted") or m.get("match_status") or ""
                if mid:
                    results.append({"id": mid, "title": title, "score": score, "status": str(status)})
            if results:
                return results
    except Exception:
        # ignore and continue to try other APIs
        pass

    # 2) Try legacy cricapi.com API (http://cricapi.com/api/cricket)
    try:
        url = f"http://cricapi.com/api/cricket?apikey={CRICKET_API_KEY}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            j = r.json()
            data = j.get("data") or []
            for item in data:
                mid = str(item.get("unique_id") or item.get("uniqueId") or "")
                title = item.get("title") or item.get("description") or ""
                # we may need to call cricketScore endpoint separately to get score
                results.append({"id": mid, "title": title, "score": item.get("score",""), "status": item.get("description","")})
            if results:
                return results
    except Exception:
        pass

    # 3) If nothing, return None
    return None

def fetch_score_for_match(match_id):
    """
    Fetch latest score for one match id. Return string of score/status or None.
    We attempt known endpoints — adapt per your provider.
    """
    # try modern v1 score endpoint pattern
    try:
        url = f"https://api.cricapi.com/v1/matches/{match_id}?apikey={CRICKET_API_KEY}"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            j = r.json()
            # parse likely fields
            score = j.get("score") or j.get("data", {}).get("score") or j.get("match", {}).get("score") or ""
            if score:
                return score
    except Exception:
        pass

    # try legacy cricketScore endpoint
    try:
        url = f"http://cricapi.com/api/cricketScore?unique_id={match_id}&apikey={CRICKET_API_KEY}"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            j = r.json()
            score = j.get("score") or j.get("data", {}).get("score") or ""
            return score
    except Exception:
        pass

    return None

# ========== Weather helper ==========
def get_weather(city_name):Khulna
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=bn"
        r = requests.get(url, timeout=8)
        if r.status_code != 200:
            return None
        j = r.json()
        desc = j.get("weather",[{}])[0].get("description","")
        temp = j.get("main",{}).get("temp")
        humidity = j.get("main",{}).get("humidity")
        wind = j.get("wind",{}).get("speed")
        return {"desc": desc, "temp": temp, "humidity": humidity, "wind": wind}
    except Exception:
        return None

# ========== Bot Handlers ==========
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    add_user(message.chat.id, message.from_user.first_name or "")
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🏏 লাইভ ম্যাচ লিস্ট", callback_data="list_matches"))
    markup.add(types.InlineKeyboardButton("🌤 আবহাওয়া", callback_data="ask_weather"))
    markup.add(types.InlineKeyboardButton("🎮 গেমস", callback_data="games"))
    markup.add(types.InlineKeyboardButton("🔔 আমার সাবস্ক্রিপশন", callback_data="my_subs"))
    bot.send_message(message.chat.id,
                     "👋 স্বাগতম! আমি লাইভ ক্রিকেট + আবহাওয়া বট 🤖\n\n"
                     "Use the menu below বা কমান্ড লিখো:\n"
                     "/matches - লাইভ ম্যাচ লিস্ট\n"
                     "/subscriptions - তোমার সাবস্ক্রিপশন দেখো\n"
                     "/help - নির্দেশনা",
                     reply_markup=markup)

@bot.message_handler(commands=['matches'])
def cmd_matches(message):
    send_match_list(message.chat.id)

@bot.message_handler(commands=['subscriptions'])
def cmd_subscriptions(message):
    subs = get_user_subscriptions(message.chat.id)
    if not subs:
        bot.send_message(message.chat.id, "তুমি কোনো ম্যাচে সাবস্ক্রাইব করো নাই। /matches দিয়ে সাবস্ক্রাইব করো।")
        return
    text = "🔔 তোমার সাবস্ক্রিপশন:\n\n"
    for s in subs:
        text += f"• {s[1]} (id: {s[0]})\n"
    bot.send_message(message.chat.id, text)

@bot.callback_query_handler(func=lambda c: True)
def on_callback(call):
    try:
        if call.data == "list_matches":
            send_match_list(call.message.chat.id)
        elif call.data.startswith("subscribe_"):
            match_id = call.data.split("_",1)[1]
            match_title = call.message.text.split("\n")[0] if call.message and call.message.text else "Match"
            add_subscription(call.message.chat.id, match_id, match_title)
            bot.answer_callback_query(call.id, "Subscribed to match ✅")
            bot.send_message(call.message.chat.id, f"✅ তুমি সাবস্ক্রাইব করেছো: {match_title} (id: {match_id})")
        elif call.data.startswith("unsubscribe_"):
            match_id = call.data.split("_",1)[1]
            remove_subscription(call.message.chat.id, match_id)
            bot.answer_callback_query(call.id, "Unsubscribed ✅")
            bot.send_message(call.message.chat.id, f"সাবস্ক্রিপশন বাতিল হয়েছে: {match_id}")
        elif call.data == "ask_weather":
            bot.send_message(call.message.chat.id, "শহরের নাম লিখো (উদাহরণ: Dhaka বা Kolkata):")
        elif call.data == "games":
            game_markup = types.InlineKeyboardMarkup()
            game_markup.add(types.InlineKeyboardButton("🎲 Guess Number", callback_data="game_guess"))
            game_markup.add(types.InlineKeyboardButton("❓ Quick Quiz", callback_data="game_quiz"))
            bot.send_message(call.message.chat.id, "গেম সিলেক্ট করো:", reply_markup=game_markup)
        elif call.data == "game_guess":
            number = random.randint(1, 10)
            bot.send_message(call.message.chat.id, "আমি 1-10 এর মধ্যে একটি সংখ্যা ভেবেছি। অনুমান করো:")
            bot.register_next_step_handler(call.message, lambda m: handle_guess(m, number))
        elif call.data == "game_quiz":
            bot.send_message(call.message.chat.id, "কুইজ: বাংলাদেশের জাতীয় পশু কোনটি?\nA) বাঘ\nB) মহিষ\nC) শিয়াল")
        elif call.data == "my_subs":
            cmd_subscriptions(call.message)
    except Exception as e:
        traceback.print_exc()
        bot.send_message(call.message.chat.id, "একটি ত্রুটি ঘটেছে।")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    txt = message.text.strip()
    lower = txt.lower()

    # Weather quick input (if message looks like a city name - letters and maybe spaces)
    if len(txt) > 1 and all(ch.isalpha() or ch.isspace() for ch in txt):
        w = get_weather(txt)
        if w:
            bot.send_message(message.chat.id,
                             f"🌤 {txt.title()}:\n{w['desc']}\nতাপমাত্রা: {w['temp']}°C\nআর্দ্রতা: {w['humidity']}%\nহাওয়া: {w['wind']} m/s")
            return

    # quiz answers
    if lower in ["a", "বাঘ", "bagh"]:
        bot.send_message(message.chat.id, "✅ সঠিক! জাতীয় পশু — বাঘ।")
        return
    if lower in ["b", "মহিষ", "mohish", "mohis"]:
        bot.send_message(message.chat.id, "❌ ভুল। আবার চেষ্টা করো।")
        return

    # other commands
    bot.send_message(message.chat.id, "আমি বুঝতে পারিনি। /help লিখে মেনু দেখো।")

def handle_guess(message, number):
    try:
        guess = int(message.text.strip())
        if guess == number:
            bot.send_message(message.chat.id, "🎉 বাহ! ঠিক ধরেছো!")
        else:
            bot.send_message(message.chat.id, f"✖️ ভুল। আমি ভেবেছিলাম {number}")
    except:
        bot.send_message(message.chat.id, "সংখ্যা লিখো (1-10) পুনরায় চেষ্টা করো।")

# ========== Helper to send matches ==========

def send_match_list(chat_id):
    matches = fetch_current_matches()
    if not matches:
        bot.send_message(chat_id, "কোনো লাইভ ম্যাচ পাওয়া যায়নি অথবা API তে সমস্যা আছে।")
        return
    # show a list with subscribe buttons
    for m in matches:
        title = m.get("title") or "ম্যাচ"
        score = m.get("score") or ""
        status = m.get("status") or ""
        text = f"{title}\n{score}\n{status}\n\nID: {m.get('id')}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔔 Subs       cribe", callback_data=f"subscribe_{m.get('id')}"))
        markup.add(types.InlineKeyboardButton("❌ Unsubscribe", callback_data=f"unsubscribe_{m.get('id')}"))
        bot.send_message(chat_id, text, reply_markup=markup)

# ========== Background poller (send updates to subscribers) ==========

def poller_worker():
    while True:
        try:
            subs_by_match = {}
            # get all distinct match ids from DB
            conn = sqlite3.connect(DATABASE_FILE)
            c = conn.cursor()
            c.execute('SELECT DISTINCT match_id FROM subscriptions')
            rows = c.fetchall()
            conn.close()
            match_ids = [r[0] for r in rows if r[0]]

            for mid in match_ids:
                try:
                    latest = fetch_score_for_match(mid)
                    if not latest:
                        continue
                    # get subscribers
                    subs = get_subscriptions_for_match(mid)
                    for (chat_id, last_score) in subs:
                        # if changed, send update
                        if latest != (last_score or ""):
                            try:
                                bot.send_message(chat_id, f"🔔 Match Update (id:{mid}):\n{latest}")
                                update_last_score(chat_id, mid, latest)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            traceback.print_exc()
        time.sleep(POLL_INTERVAL)

# ========== Startup ==========
if __name__ == "__main__":
    print("Initializing DB...")
    init_db()
    # start poller thread
    t = threading.Thread(target=poller_worker, daemon=True)
    t.start()
    print("Bot is running...")

    bot.infinity_polling()
