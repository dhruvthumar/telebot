import telebot
import os
import threading
import time
import logging
from datetime import datetime, timedelta

# Configure logging to output to console (Render logs this automatically)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger()

# Bot configuration
BOT_TOKEN = os.getenv('7777704982:AAENdawbGbre5MjIP9F6ckBV2g3EiELBRj4')  # Set this in Render environment variables
bot = telebot.TeleBot(BOT_TOKEN)

# In-memory ride storage (resets on app restart)
rides = []

def get_user_identifier(message):
    return f"@{message.from_user.username}" if message.from_user.username else f"User {message.chat.id}"

def format_datetime(dt_str):
    """Convert 'YYYY-MM-DD HH:MM:SS' to 'MMM DD H:MM AM/PM' (e.g., 'Apr 3 10:30 PM')."""
    dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
    return dt.strftime('%b %d %I:%M %p').replace(' 0', ' ')

def parse_ride_input(text):
    """Parse natural language input into event, date (ddmm), and time."""
    text = text.lower().strip()
    current_year = datetime.now().year

    months = {
        'january': '01', 'jan': '01', 'february': '02', 'feb': '02', 'march': '03', 'mar': '03',
        'april': '04', 'apr': '04', 'may': '05', 'june': '06', 'jun': '06', 'july': '07', 'jul': '07',
        'august': '08', 'aug': '08', 'september': '09', 'sep': '09', 'october': '10', 'oct': '10',
        'november': '11', 'nov': '11', 'december': '12', 'dec': '12'
    }

    if ' at ' in text:
        event_part, time_part = text.split(' at ', 1)
    else:
        raise ValueError("Missing 'at' for time. Use something like 'Rinku on Apr 3 at 22:30'.")

    if ' on ' in event_part:
        event = event_part.split(' on ')[0].strip()
        date_part = event_part.split(' on ')[1].strip()
    else:
        event = event_part.strip()
        today = datetime.now()
        return event, f"{today.day:02d}{today.month:02d}", time_part

    for month_name, month_num in months.items():
        if month_name in date_part:
            day_str = date_part.replace(month_name, '').replace(',', '').strip()
            if day_str.isdigit() and 1 <= int(day_str) <= 31:
                return event, f"{day_str.zfill(2)}{month_num}", time_part
            for suffix in ['st', 'nd', 'rd', 'th']:
                if day_str.endswith(suffix):
                    day = day_str[:-2]
                    if day.isdigit() and 1 <= int(day) <= 31:
                        return event, f"{day.zfill(2)}{month_num}", time_part
            break

    parts = date_part.split()
    if len(parts) >= 2:
        day_str = parts[0]
        month_candidate = parts[1]
        if month_candidate in months:
            if day_str.isdigit() and 1 <= int(day_str) <= 31:
                return event, f"{day_str.zfill(2)}{months[month_candidate]}", time_part
            for suffix in ['st', 'nd', 'rd', 'th']:
                if day_str.endswith(suffix):
                    day = day_str[:-2]
                    if day.isdigit() and 1 <= int(day) <= 31:
                        return event, f"{day.zfill(2)}{months[month_candidate]}", time_part

    raise ValueError("Invalid date format. Use 'Apr 3', '3 April', '3rd Apr', etc.")

def parse_time(time_str):
    """Convert time like '22:30', '10:30pm', '10pm' to 'hh:mm'."""
    time_str = time_str.strip().replace(' ', '')
    try:
        time_obj = datetime.strptime(time_str, '%H:%M')  # e.g., "22:30"
    except ValueError:
        if 'am' in time_str or 'pm' in time_str:
            time_str = time_str.replace('am', ' AM').replace('pm', ' PM')
            try:
                time_obj = datetime.strptime(time_str, '%I:%M %p')  # e.g., "10:30 PM"
            except ValueError:
                time_obj = datetime.strptime(time_str, '%I %p')  # e.g., "10 PM"
        else:
            raise ValueError("Invalid time format. Use '22:30', '10:30pm', or '10pm'.")
    return f"{time_obj.hour:02d}:{time_obj.minute:02d}"

@bot.message_handler(commands=['home'])
def handle_home_command(message):
    user = get_user_identifier(message)
    logger.info(f"{user} ran /home")
    bot.reply_to(message, "This command only works on the Raspberry Pi with home.py. Host me locally for full functionality!")

@bot.message_handler(commands=['cpu'])
def handle_cpu_command(message):
    user = get_user_identifier(message)
    logger.info(f"{user} ran /cpu")
    bot.reply_to(message, "This command only works on the Raspberry Pi with logger.py. Host me locally for full functionality!")

@bot.message_handler(commands=['start'])
def handle_start_command(message):
    user = get_user_identifier(message)
    logger.info(f"{user} ran /start")
    bot.reply_to(message, "Welcome! Use /ride, /rides, /delride. Example: /ride Rinku on Apr 3 at 22:30\n/cpu and /home work only on Pi.")

@bot.message_handler(commands=['ride'])
def handle_ride_command(message):
    user = get_user_identifier(message)
    logger.info(f"{user} ran /ride: {message.text}")
    try:
        text = message.text[len('/ride'):].strip()
        if not text:
            bot.reply_to(message, "Usage: /ride <event> on <date> at <time>\nExample: /ride Rinku on Apr 3 at 22:30")
            return
        
        event, date_str, time_part = parse_ride_input(text)
        time_str = parse_time(time_part)
        year = datetime.now().year
        day, month = int(date_str[:2]), int(date_str[2:])
        hour, minute = map(int, time_str.split(':'))
        ride_datetime = datetime(year, month, day, hour, minute)

        if ride_datetime.year != year:
            raise ValueError(f"Rides must be for {year}. Adjust your date.")

        ride = {
            'id': len(rides) + 1,
            'event': event,
            'datetime': ride_datetime.strftime('%Y-%m-%d %H:%M:%S'),
            'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'chat_id': message.chat.id,
            'reminded_1day': False,
            'reminded_1hour': False,
            'reminded_10min': False
        }
        rides.append(ride)
        bot.reply_to(message, f"Ride added: {event} on {format_datetime(ride['datetime'])}")
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}\nExample: /ride Rinku on Apr 3 at 22:30")

@bot.message_handler(commands=['rides'])
def handle_rides_command(message):
    user = get_user_identifier(message)
    logger.info(f"{user} ran /rides")
    try:
        user_rides = [ride for ride in rides if ride['chat_id'] == message.chat.id]
        if not user_rides:
            bot.reply_to(message, "No rides found for you.")
            return
        response = "🚗 Your Rides:\n"
        for ride in user_rides:
            response += f"{ride['id']}. {ride['event']} - Due: {format_datetime(ride['datetime'])}\n"
        bot.reply_to(message, response)
    except Exception as e:
        bot.reply_to(message, f"Error loading rides: {str(e)}")

@bot.message_handler(commands=['delride'])
def handle_delride_command(message):
    user = get_user_identifier(message)
    logger.info(f"{user} ran /delride: {message.text}")
    try:
        text = message.text[len('/delride'):].strip()
        if not text or not text.isdigit():
            bot.reply_to(message, "Usage: /delride <ride_id>\nExample: /delride 1")
            return
        ride_id = int(text)
        global rides
        original_len = len(rides)
        rides = [ride for ride in rides if not (ride['id'] == ride_id and ride['chat_id'] == message.chat.id)]
        if len(rides) == original_len:
            bot.reply_to(message, f"No ride found with ID {ride_id} that belongs to you.")
            return
        bot.reply_to(message, f"Ride {ride_id} deleted successfully.")
    except Exception as e:
        bot.reply_to(message, f"Error: {str(e)}\nUsage: /delride <ride_id>")

def check_rides():
    while True:
        try:
            global rides
            now = datetime.now()
            updated = False

            rides_to_keep = []
            for ride in rides:
                if not all(key in ride for key in ['id', 'event', 'datetime', 'chat_id']):
                    logger.warning(f"Skipping invalid ride: {ride.get('id', 'unknown')} - missing required fields")
                    continue
                ride_dt = datetime.strptime(ride['datetime'], '%Y-%m-%d %H:%M:%S')
                chat_id = ride['chat_id']
                time_until = ride_dt - now

                one_day = timedelta(days=1)
                one_hour = timedelta(hours=1)
                ten_minutes = timedelta(minutes=10)

                if not ride.get('reminded_1day', False) and one_day - timedelta(minutes=1) <= time_until <= one_day + timedelta(minutes=1):
                    bot.send_message(chat_id, f"⏰ Ride Reminder: '{ride['event']}' is in 1 day ({format_datetime(ride['datetime'])})")
                    ride['reminded_1day'] = True
                    updated = True
                    logger.info(f"Sent 1-day reminder for ride {ride['id']} to chat_id {chat_id}")

                if not ride.get('reminded_1hour', False) and one_hour - timedelta(minutes=1) <= time_until <= one_hour + timedelta(minutes=1):
                    bot.send_message(chat_id, f"⏰ Ride Reminder: '{ride['event']}' is in 1 hour ({format_datetime(ride['datetime'])})")
                    ride['reminded_1hour'] = True
                    updated = True
                    logger.info(f"Sent 1-hour reminder for ride {ride['id']} to chat_id {chat_id}")

                if not ride.get('reminded_10min', False) and ten_minutes - timedelta(minutes=1) <= time_until <= ten_minutes + timedelta(minutes=1):
                    bot.send_message(chat_id, f"⏰ Ride Reminder: '{ride['event']}' is in 10 minutes ({format_datetime(ride['datetime'])})")
                    ride['reminded_10min'] = True
                    updated = True
                    logger.info(f"Sent 10-min reminder for ride {ride['id']} to chat_id {chat_id}")

                if now >= ride_dt:
                    logger.info(f"Deleting expired ride {ride['id']} for {ride['event']} at {format_datetime(ride['datetime'])}")
                    updated = True
                else:
                    rides_to_keep.append(ride)

            if updated:
                rides = rides_to_keep
        except Exception as e:
            logger.error(f"Error in ride check thread: {type(e).__name__} - {str(e)}")
            time.sleep(10)
        time.sleep(10)

def main():
    logger.info("Bot starting...")
    ride_thread = threading.Thread(target=check_rides, daemon=True)
    ride_thread.start()
    logger.info("Ride check thread started successfully")
    bot.delete_webhook()
    logger.info("Webhook deleted successfully")
    bot.polling(none_stop=True, interval=0, timeout=60)

if __name__ == "__main__":
    main()
