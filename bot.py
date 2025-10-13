# advanced_cricket_bot.py
import telebot
from telebot import types
import requests
import random
import threading
import time
import traceback

# ================== CONFIG ==================
# API keys are hardcoded directly into the script.
# This is simpler for personal use but less secure for public repositories.
TELEGRAM_TOKEN = "7833033071:AAH-3RtBLk6JCV66JKHmPLalAErgAsFuv0g"
CRICKET_API_KEY  = "va5IlHSAJTNy7o368jHuS2SYUbXSGMPFtbMzED9SDtnoTd0b3rNhAI42IF2s"
WEATHER_API_KEY  = "b6907d289e10d714a6e88b30761fae22"
POLL_INTERVAL    = 30   # seconds between polling the cricket API for score updates
# ============================================

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ========== In-Memory Data Storage (No Database) ==========
# WARNING: This data is not persistent. It will be lost if the bot is restarted.
data_lock = threading.Lock()
users_data = set()
subscriptions_data = {}

# ========== Data Helper Functions (In-Memory Version) ==========
def add_user(chat_id, name):
    """Adds a user's chat_id to the in-memory set."""
    with data_lock:
        users_data.add(chat_id)
    print(f"User added/active: {chat_id}")

def add_subscription(chat_id, match_id, match_title):
    """Adds a match subscription for a user."""
    with data_lock:
        if chat_id not in subscriptions_data:
            subscriptions_data[chat_id] = {}
        subscriptions_data[chat_id][match_id] = {
            "title": match_title,
            "last_score": ""
        }

def remove_subscription(chat_id, match_id):
    """Removes a match subscription for a user."""
    with data_lock:
        if chat_id in subscriptions_data and match_id in subscriptions_data[chat_id]:
            del subscriptions_data[chat_id][match_id]
            if not subscriptions_data[chat_id]:
                del subscriptions_data[chat_id]

def get_subscriptions_for_match(match_id):
    """Finds all users subscribed to a specific match_id."""
    subscribers = []
    with data_lock:
        for chat_id, user_subs in subscriptions_data.items():
            if match_id in user_subs:
                last_score = user_subs[match_id].get("last_score", "")
                subscribers.append((chat_id, last_score))
    return subscribers

def update_last_score(chat_id, match_id, new_score):
    """Updates the last known score for a specific subscription."""
    with data_lock:
        if chat_id in subscriptions_data and match_id in subscriptions_data[chat_id]:
            subscriptions_data[chat_id][match_id]['last_score'] = new_score

def get_user_subscriptions(chat_id):
    """Gets all match subscriptions for a given user."""
    with data_lock:
        user_subs = subscriptions_data.get(chat_id, {})
        return [(match_id, details['title']) for match_id, details in user_subs.items()]

# ========== Cricket API helpers ==========
def fetch_current_matches():
    """Fetches current matches from the API."""
    results = []
    try:
        url = f"https://api.cricapi.com/v1/currentMatches?apikey={CRICKET_API_KEY}&offset=0"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        j = r.json()
        data = j.get("data", [])
        for m in data:
            mid = str(m.get("id") or m.get("unique_id") or "")
            teams = m.get("teams", [])
            team1 = m.get("t1", "Team 1")
            team2 = m.get("t2", "Team 2")
            title = f"{teams[0]} vs {teams[1]}" if len(teams) == 2 else m.get("name", f"{team1} vs {team2}")
            score_info = m.get("score", [])
            score_str = ", ".join([f"{s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)" for s in score_info]) if score_info else "Score not available"
            status = m.get("status", "Status not available")
            if mid:
                results.append({"id": mid, "title": title, "score": score_str, "status": status})
        return results if results else None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from CricAPI v1: {e}")
    except Exception as e:
        print(f"An unexpected error occurred with CricAPI v1: {e}")
    return None


def fetch_score_for_match(match_id):
    """Fetches the latest score for a single match."""
    try:
        url = f"https://api.cricapi.com/v1/match_info/{match_id}?apikey={CRICKET_API_KEY}"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data = r.json().get("data", {})
        if not data: return None
        score_info = data.get("score", [])
        score_str = ", ".join([f"{s.get('r',0)}/{s.get('w',0)} ({s.get('o',0)} ov)" for s in score_info]) if score_info else "Score not available"
        status = data.get("status", "Status not available")
        return f"{score_str}\nStatus: {status}"
    except requests.exceptions.RequestException as e:
        print(f"Error fetching score for match {match_id}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred fetching score for {match_id}: {e}")
    return None

# ========== Weather helper ==========
def get_weather(city_name):
    """Fetches weather data for a given city."""
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={WEATHER_API_KEY}&units=metric&lang=bn"
        r = requests.get(url, timeout=8)
        if r.status_code != 200: return None
        j = r.json()
        desc = j.get("weather",[{}])[0].get("description","")
        temp = j.get("main",{}).get("temp")
        humidity = j.get("main",{}).get("humidity")
        wind = j.get("wind",{}).get("speed")
        return {"desc": desc, "temp": temp, "humidity": humidity, "wind": wind}
    except Exception as e:
        print(f"Weather API error: {e}")
        return None

# ========== Bot Handlers ==========
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    add_user(message.chat.id, message.from_user.first_name or "")
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🏏 লাইভ ম্যাচ লিস্ট", callback_data="list_matches"))
    markup.add(types.InlineKeyboardButton("🌤 আবহাওয়া দেখুন", callback_data="ask_weather"))
    markup.add(types.InlineKeyboardButton("🎮 মজার গেমস", callback_data="games"))
    markup.add(types.InlineKeyboardButton("🔔 আমার সাবস্ক্রিপশন", callback_data="my_subs"))
    bot.send_message(message.chat.id,
                     "👋 স্বাগতম! আমি একটি অ্যাডভান্সড ক্রিকেট ও আবহাওয়া বট। 🤖\n\n"
                     "নিচের মেনু ব্যবহার করুন অথবা কমান্ড লিখুন:\n"
                     "/matches - সব লাইভ ম্যাচের তালিকা দেখুন।\n"
                     "/subscriptions - আপনার সাবস্ক্রাইব করা ম্যাচগুলো দেখুন।\n"
                     "/help - এই সাহায্য মেনুটি আবার দেখুন।",
                     reply_markup=markup)

@bot.message_handler(commands=['matches'])
def cmd_matches(message):
    send_match_list(message.chat.id)

@bot.message_handler(commands=['subscriptions'])
def cmd_subscriptions(message):
    subs = get_user_subscriptions(message.chat.id)
    if not subs:
        bot.send_message(message.chat.id, "আপনি এখনো কোনো ম্যাচে সাবস্ক্রাইব করেননি। /matches কমান্ড ব্যবহার করে নতুন ম্যাচে সাবস্ক্রাইব করুন।")
        return
    text = "🔔 আপনার সকল সাবস্ক্রিপশন:\n\n"
    for match_id, match_title in subs:
        text += f"• {match_title} (ID: {match_id})\n"
    bot.send_message(message.chat.id, text)

@bot.callback_query_handler(func=lambda call: True)
def on_callback(call):
    try:
        action, _, payload = call.data.partition('_')

        if action == "list" and payload == "matches":
            bot.answer_callback_query(call.id, "ম্যাচ লোড হচ্ছে...")
            send_match_list(call.message.chat.id)
        elif action == "subscribe":
            match_id = payload
            match_title = "Unknown Match"
            if call.message and call.message.text:
                lines = call.message.text.split('\n')
                if lines: match_title = lines[0].strip('*')
            add_subscription(call.message.chat.id, match_id, match_title)
            bot.answer_callback_query(call.id, "✅ সাবস্ক্রাইব করা হয়েছে!")
            bot.send_message(call.message.chat.id, f"✅ আপনি সফলভাবে সাবস্ক্রাইব করেছেন: {match_title}")
        elif action == "unsubscribe":
            match_id = payload
            remove_subscription(call.message.chat.id, match_id)
            bot.answer_callback_query(call.id, "❌ আনসাবস্ক্রাইব করা হয়েছে")
            bot.send_message(call.message.chat.id, "সাবস্ক্রিপশন বাতিল করা হয়েছে।")
        elif action == "ask" and payload == "weather":
            bot.answer_callback_query(call.id)
            bot.send_message(call.message.chat.id, "আপনার শহরের নাম লিখুন (যেমন: Dhaka):")
        elif action == "games":
            bot.answer_callback_query(call.id)
            game_markup = types.InlineKeyboardMarkup()
            game_markup.add(types.InlineKeyboardButton("🎲 সংখ্যা অনুমান", callback_data="game_guess"))
            game_markup.add(types.InlineKeyboardButton("❓ কুইজ", callback_data="game_quiz"))
            bot.edit_message_text("একটি গেম বেছে নিন:", call.message.chat.id, call.message.message_id, reply_markup=game_markup)
        elif action == "game":
            if payload == "guess":
                bot.answer_callback_query(call.id)
                number = random.randint(1, 10)
                msg = bot.send_message(call.message.chat.id, "আমি ১ থেকে ১০ এর মধ্যে একটি সংখ্যা ভেবেছি। অনুমান করে বলুন তো সংখ্যাটি কত?")
                bot.register_next_step_handler(msg, lambda m: handle_guess(m, number))
            elif payload == "quiz":
                bot.answer_callback_query(call.id)
                bot.send_message(call.message.chat.id, "কুইজ: বাংলাদেশের জাতীয় পশুর নাম কী?\nA) রয়েল বেঙ্গল টাইগার\nB) হরিণ\nC) হাতি")
        elif action == "my" and payload == "subs":
            bot.answer_callback_query(call.id)
            cmd_subscriptions(call.message)

    except Exception as e:
        print(f"Error in callback handler: {e}")
        traceback.print_exc()
        bot.send_message(call.message.chat.id, "দুঃখিত, একটি অপ্রত্যাশিত ত্রুটি ঘটেছে।")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    txt = message.text.strip()
    lower = txt.lower()

    if len(txt) > 1 and all(c.isalpha() or c.isspace() for c in txt):
        bot.send_chat_action(message.chat.id, 'typing')
        weather_data = get_weather(txt)
        if weather_data:
            response = (
                f"🌤 {txt.title()} শহরের আবহাওয়া:\n"
                f"-----------------------------------\n"
                f"🌦 বিবরণ: {weather_data['desc']}\n"
                f"🌡 তাপমাত্রা: {weather_data['temp']}°C\n"
                f"💧 আর্দ্রতা: {weather_data['humidity']}%\n"
                f"💨 বায়ুপ্রবাহ: {weather_data['wind']} m/s"
            )
            bot.send_message(message.chat.id, response)
            return

    if any(keyword in lower for keyword in ["a", "টাইগার", "bagh", "royal bengal tiger"]):
        bot.send_message(message.chat.id, "✅ সঠিক উত্তর! বাংলাদেশের জাতীয় পশু রয়েল বেঙ্গল টাইগার।")
        return
    elif any(keyword in lower for keyword in ["b", "c", "হরিণ", "হাতি"]):
        bot.send_message(message.chat.id, "❌ উত্তরটি ভুল। আবার চেষ্টা করুন।")
        return

    bot.send_message(message.chat.id, "দুঃখিত, আমি আপনার কথা বুঝতে পারিনি। /help কমান্ড লিখে মেনু দেখুন।")

def handle_guess(message, correct_number):
    try:
        guess = int(message.text.strip())
        if guess == correct_number:
            bot.send_message(message.chat.id, f"🎉 অসাধারণ! আপনি সঠিক অনুমান করেছেন! সংখ্যাটি ছিল {correct_number}।")
        else:
            bot.send_message(message.chat.id, f"✖️ দুঃখিত, উত্তরটি ভুল। আমি যে সংখ্যাটি ভেবেছিলাম তা হলো {correct_number}।")
    except (ValueError, TypeError):
        bot.send_message(message.chat.id, "দয়া করে একটি সংখ্যা (যেমন: 5) লিখুন। আবার চেষ্টা করতে চাইলে গেম মেনু থেকে খেলাটি শুরু করুন।")

# ========== Helper to send matches ==========
def send_match_list(chat_id):
    matches = fetch_current_matches()
    if not matches:
        bot.send_message(chat_id, "এই মুহূর্তে কোনো লাইভ ম্যাচ খুঁজে পাওয়া যায়নি অথবা API সংযোগে সমস্যা হয়েছে।")
        return
    bot.send_message(chat_id, "🏏 বর্তমানে চলমান ম্যাচসমূহ:")
    for m in matches:
        text = f"**{m.get('title', 'Unknown Match')}**\n\n*Score:*\n{m.get('score')}\n\n*Status:*\n{m.get('status')}"
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🔔 সাবস্ক্রাইব করুন", callback_data=f"subscribe_{m.get('id')}"),
            types.InlineKeyboardButton("❌ আনসাবস্ক্রাইব", callback_data=f"unsubscribe_{m.get('id')}")
        )
        bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")
        time.sleep(0.1)

# ========== Background Poller (sends updates to subscribers) ==========
def poller_worker():
    print("Background poller thread started.")
    while True:
        try:
            with data_lock:
                all_subscribed_match_ids = {
                    match_id for user_subs in subscriptions_data.values() for match_id in user_subs.keys()
                }

            if not all_subscribed_match_ids:
                time.sleep(POLL_INTERVAL)
                continue

            for mid in all_subscribed_match_ids:
                try:
                    latest_score_details = fetch_score_for_match(mid)
                    if not latest_score_details: continue
                    subscribers = get_subscriptions_for_match(mid)
                    for chat_id, last_known_score in subscribers:
                        if latest_score_details != last_known_score:
                            try:
                                with data_lock:
                                    title = subscriptions_data.get(chat_id, {}).get(mid, {}).get('title', f'Match ID: {mid}')
                                bot.send_message(chat_id, f"🔔 **স্কোর আপডেট: {title}**\n\n{latest_score_details}", parse_mode="Markdown")
                                update_last_score(chat_id, mid, latest_score_details)
                                time.sleep(0.2)
                            except Exception as send_err:
                                print(f"Failed to send update to {chat_id}: {send_err}")
                except Exception as inner_loop_err:
                    print(f"Error processing match ID {mid} in poller: {inner_loop_err}")
        except Exception as outer_loop_err:
            print(f"Major error in poller_worker loop: {outer_loop_err}")
        time.sleep(POLL_INTERVAL)

# ========== Startup ==========
if __name__ == "__main__":
    print("Starting bot with polling and in-memory storage...")
    # Start the background poller thread for score updates.
    poller_thread = threading.Thread(target=poller_worker, daemon=True)
    poller_thread.start()

    print("Bot is now running using polling. Press Ctrl+C to stop.")
    # This will run the bot continuously. skip_pending=True ignores messages sent while the bot was offline.
    bot.infinity_polling(skip_pending=True)

