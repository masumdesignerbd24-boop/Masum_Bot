# ===============================================
# 📦 advanced_cricket_bot.py
# উন্নত বাংলা UI + পোর্ট লিসেনিং (Flask সার্ভারসহ)
# ===============================================

import telebot
from telebot import types
import requests
import threading
import time
import random
import traceback
from flask import Flask, request

================== CONFIG ==================
# API keys are hardcoded directly into the script.
# This is simpler for personal use but less secure for public repositories.
TELEGRAM_TOKEN = "7833033071:AAH-3RtBLk6JCV66JKHmPLalAErgAsFuv0g"
CRICKET_API_KEY  = "va5IlHSAJTNy7o368jHuS2SYUbXSGMPFtbMzED9SDtnoTd0b3rNhAI42IF2s"
WEATHER_API_KEY  = "b6907d289e10d714a6e88b30761fae22"
POLL_INTERVAL    = 30   # seconds between polling the cricket API for score updates

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode="Markdown")

# In-memory storage (non-persistent)
data_lock = threading.Lock()
users_data = set()
subscriptions_data = {}

# ===============================================
# 🧩 Data helper functions
# ===============================================
def add_user(chat_id):
    with data_lock:
        users_data.add(chat_id)

def add_subscription(chat_id, match_id, match_title):
    with data_lock:
        if chat_id not in subscriptions_data:
            subscriptions_data[chat_id] = {}
        subscriptions_data[chat_id][match_id] = {"title": match_title, "last_score": ""}

def remove_subscription(chat_id, match_id):
    with data_lock:
        if chat_id in subscriptions_data and match_id in subscriptions_data[chat_id]:
            del subscriptions_data[chat_id][match_id]
            if not subscriptions_data[chat_id]:
                del subscriptions_data[chat_id]

def get_user_subscriptions(chat_id):
    with data_lock:
        return [(mid, d['title']) for mid, d in subscriptions_data.get(chat_id, {}).items()]

def update_last_score(chat_id, match_id, new_score):
    with data_lock:
        if chat_id in subscriptions_data and match_id in subscriptions_data[chat_id]:
            subscriptions_data[chat_id][match_id]['last_score'] = new_score

def get_subscriptions_for_match(match_id):
    subs = []
    with data_lock:
        for chat_id, user_subs in subscriptions_data.items():
            if match_id in user_subs:
                subs.append((chat_id, user_subs[match_id]['last_score']))
    return subs

# ===============================================
# 🏏 Cricket API
# ===============================================
def fetch_current_matches():
    try:
        url = f"https://api.cricapi.com/v1/currentMatches?apikey={CRICKET_API_KEY}&offset=0"
        res = requests.get(url, timeout=10).json()
        data = res.get("data", [])
        matches = []
        for m in data:
            mid = str(m.get("id") or "")
            teams = m.get("teams", [])
            title = f"{teams[0]} vs {teams[1]}" if len(teams) == 2 else m.get("name", "Unknown Match")
            score_info = m.get("score", [])
            score_str = ", ".join([f"{s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)" for s in score_info]) or "স্কোর পাওয়া যায়নি"
            matches.append({"id": mid, "title": title, "score": score_str, "status": m.get("status", "N/A")})
        return matches
    except Exception as e:
        print("Cricket API error:", e)
        return None

def fetch_score_for_match(match_id):
    try:
        url = f"https://api.cricapi.com/v1/match_info/{match_id}?apikey={CRICKET_API_KEY}"
        r = requests.get(url, timeout=8)
        data = r.json().get("data", {})
        if not data: return None
        score_info = data.get("score", [])
        score_str = ", ".join([f"{s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)" for s in score_info])
        return f"{score_str}\n🕓 অবস্থা: {data.get('status','N/A')}"
    except Exception as e:
        print("Score fetch error:", e)
        return None

# ===============================================
# 🌤 Weather API
# ===============================================
def get_weather(city_name):
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=bn"
        r = requests.get(url, timeout=8)
        j = r.json()
        desc = j["weather"][0]["description"]
        temp = j["main"]["temp"]
        hum = j["main"]["humidity"]
        wind = j["wind"]["speed"]
        return f"🌤 *{city_name.title()} শহরের আবহাওয়া*\n\n🌦 অবস্থা: {desc}\n🌡 তাপমাত্রা: {temp}°C\n💧 আর্দ্রতা: {hum}%\n💨 বায়ু: {wind} m/s"
    except:
        return None

# ===============================================
# 🤖 Bot Handlers
# ===============================================
@bot.message_handler(commands=['start','help'])
def start_cmd(msg):
    add_user(msg.chat.id)
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🏏 ম্যাচ লিস্ট", callback_data="matches"),
        types.InlineKeyboardButton("🌤 আবহাওয়া", callback_data="weather"),
        types.InlineKeyboardButton("🎮 গেমস", callback_data="games"),
        types.InlineKeyboardButton("🔔 সাবস্ক্রিপশন", callback_data="subs")
    )
    bot.send_message(msg.chat.id,
        "👋 স্বাগতম! আমি একটি *অ্যাডভান্সড ক্রিকেট ও আবহাওয়া বট* 🤖\n\n"
        "নিচের মেনু থেকে একটি অপশন নির্বাচন করুন:",
        reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    data = call.data
    if data == "matches": send_match_list(call.message.chat.id)
    elif data == "weather": bot.send_message(call.message.chat.id, "আপনার শহরের নাম লিখুন:")
    elif data == "games":
        gm = types.InlineKeyboardMarkup()
        gm.add(types.InlineKeyboardButton("🎲 সংখ্যা অনুমান", callback_data="game_guess"))
        bot.send_message(call.message.chat.id, "একটি গেম বেছে নিন:", reply_markup=gm)
    elif data == "subs": send_subscriptions(call.message.chat.id)
    elif data.startswith("subscribe_"):
        match_id = data.split("_")[1]
        add_subscription(call.message.chat.id, match_id, "Unknown")
        bot.send_message(call.message.chat.id, "✅ আপনি ম্যাচে সাবস্ক্রাইব করেছেন!")
    elif data.startswith("unsubscribe_"):
        match_id = data.split("_")[1]
        remove_subscription(call.message.chat.id, match_id)
        bot.send_message(call.message.chat.id, "❌ সাবস্ক্রিপশন বাতিল করা হয়েছে।")
    elif data == "game_guess":
        number = random.randint(1, 10)
        msg = bot.send_message(call.message.chat.id, "আমি ১ থেকে ১০ এর মধ্যে একটি সংখ্যা ভেবেছি, অনুমান করুন:")
        bot.register_next_step_handler(msg, lambda m: guess_game(m, number))

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    text = msg.text.strip()
    weather = get_weather(text)
    if weather:
        bot.send_message(msg.chat.id, weather)
    else:
        bot.send_message(msg.chat.id, "দুঃখিত, আমি বুঝতে পারিনি। /help ব্যবহার করুন।")

def guess_game(msg, num):
    try:
        guess = int(msg.text.strip())
        if guess == num:
            bot.send_message(msg.chat.id, f"🎉 অসাধারণ! সংখ্যাটি ছিল {num}")
        else:
            bot.send_message(msg.chat.id, f"😅 ভুল হয়েছে! সংখ্যাটি ছিল {num}")
    except:
        bot.send_message(msg.chat.id, "দয়া করে একটি বৈধ সংখ্যা লিখুন।")

def send_match_list(chat_id):
    matches = fetch_current_matches()
    if not matches:
        bot.send_message(chat_id, "এই মুহূর্তে কোনো লাইভ ম্যাচ নেই 💤")
        return
    for m in matches:
        text = f"🏏 *{m['title']}*\n\n📊 স্কোর: {m['score']}\n🕓 স্ট্যাটাস: {m['status']}"
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔔 সাবস্ক্রাইব", callback_data=f"subscribe_{m['id']}"),
            types.InlineKeyboardButton("❌ আনসাবস্ক্রাইব", callback_data=f"unsubscribe_{m['id']}")
        )
        bot.send_message(chat_id, text, reply_markup=markup)

def send_subscriptions(chat_id):
    subs = get_user_subscriptions(chat_id)
    if not subs:
        bot.send_message(chat_id, "আপনি এখনো কোনো ম্যাচে সাবস্ক্রাইব করেননি।")
    else:
        text = "🔔 আপনার সাবস্ক্রিপশনসমূহ:\n\n" + "\n".join([f"• {t}" for _, t in subs])
        bot.send_message(chat_id, text)

# ===============================================
# 🔄 Background Poller
# ===============================================
def poller_worker():
    while True:
        try:
            with data_lock:
                match_ids = {mid for u in subscriptions_data.values() for mid in u}
            for mid in match_ids:
                latest = fetch_score_for_match(mid)
                if not latest: continue
                for chat_id, last_score in get_subscriptions_for_match(mid):
                    if latest != last_score:
                        bot.send_message(chat_id, f"🔔 *আপডেট পাওয়া গেছে!*\n{latest}")
                        update_last_score(chat_id, mid, latest)
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print("Poller error:", e)
            time.sleep(POLL_INTERVAL)

# ===============================================
# 🌐 Flask Webhook Server (optional)
# ===============================================
app = Flask(__name__)

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.get_json())
    bot.process_new_updates([update])
    return "OK", 200

# ===============================================
# 🚀 Run Mode Selector
# ===============================================
if __name__ == "__main__":
    print("✅ বট শুরু হচ্ছে...")

    poller_thread = threading.Thread(target=poller_worker, daemon=True)
    poller_thread.start()

    if USE_WEBHOOK:
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL)
        print(f"🌐 Webhook মোডে চলছে (port {PORT})...")
        app.run(host="0.0.0.0", port=PORT)
    else:
        print("🤖 Polling মোডে চলছে...")
        bot.infinity_polling(skip_pending=True)
