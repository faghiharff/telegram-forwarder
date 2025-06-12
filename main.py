import os
import json
import asyncio
import time
import requests
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# --- خواندن اطلاعات از متغیرهای محیطی ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
SOURCE_CHANNELS_STR = os.environ.get("SOURCE_CHANNELS")
DESTINATION_CHANNEL = int(os.environ.get("DESTINATION_CHANNEL"))
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY")  # خودکار در GitHub Actions

# --- تبدیل رشته کانال‌های مبدا به لیست ---
SOURCE_CHANNELS = []
for ch in SOURCE_CHANNELS_STR.split(','):
    ch = ch.strip()
    try:
        SOURCE_CHANNELS.append(int(ch))
    except ValueError:
        SOURCE_CHANNELS.append(ch)

STATE_FILE = 'last_message_ids.json'
MAX_RUNTIME = 8 * 60  # 8 دقیقه (کمتر از timeout)

def trigger_next_run():
    """تریگر کردن اجرای بعدی از طریق GitHub API"""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("GitHub token or repo not available for auto-trigger")
        return
    
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json"
        }
        data = {"event_type": "run_forwarder"}
        
        # منتظر 10 دقیقه بمان
        print("Waiting 10 minutes before triggering next run...")
        time.sleep(600)  # 10 دقیقه
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 204:
            print("✓ Next run triggered successfully")
        else:
            print(f"✗ Failed to trigger next run: {response.status_code}")
    except Exception as e:
        print(f"Error triggering next run: {e}")

async def main():
    start_time = time.time()
    
    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        print("Client created successfully.")
        print(f"Starting monitoring for {MAX_RUNTIME} seconds...")

        # خواندن state
        try:
            with open(STATE_FILE, 'r') as f:
                last_ids = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            last_ids = {}
            print("No previous state found, starting fresh.")

        # حلقه اصلی
        while True:
            current_time = time.time()
            
            # چک کردن زمان باقی‌مانده
            if current_time - start_time > MAX_RUNTIME:
                print("Maximum runtime reached. Saving state and exiting...")
                break
            
            print(f"\n=== Checking messages (Runtime: {int(current_time - start_time)}s) ===")
            
            messages_processed = 0
            
            for channel_input in SOURCE_CHANNELS:
                try:
                    source_entity = await client.get_entity(channel_input)
                    str_source_id = str(source_entity.id)
                    channel_title = getattr(source_entity, 'title', str(channel_input))
                    
                    last_id = last_ids.get(str_source_id, 0)

                    if last_id == 0:
                        # اولین بار - تنظیم نقطه شروع
                        print(f"First setup for: {channel_title}")
                        latest_message = await client.get_messages(source_entity, limit=1)
                        if latest_message:
                            last_ids[str_source_id] = latest_message[0].id
                            # ذخیره فوری
                            with open(STATE_FILE, 'w') as f:
                                json.dump(last_ids, f)
                            print(f"Set starting point: {latest_message[0].id}")
                    else:
                        # پردازش پیام‌های جدید
                        new_messages = []
                        async for message in client.iter_messages(source_entity, min_id=last_id, reverse=True):
                            new_messages.append(message)
                        
                        if new_messages:
                            print(f"Found {len(new_messages)} new messages in {channel_title}")
                            
                            for message in new_messages:
                                try:
                                    await client.send_message(DESTINATION_CHANNEL, message)
                                    print(f"✓ Forwarded message {message.id}")
                                    messages_processed += 1
                                    
                                    # ذخیره فوری state بعد از هر پیام
                                    last_ids[str_source_id] = message.id
                                    with open(STATE_FILE, 'w') as f:
                                        json.dump(last_ids, f)
                                    
                                    # فاصله کوتاه
                                    await asyncio.sleep(1)
                                    
                                except Exception as e:
                                    print(f"✗ Failed to forward message {message.id}: {e}")
                                    # حتی در صورت خطا، state رو آپدیت کن
                                    last_ids[str_source_id] = message.id
                                    with open(STATE_FILE, 'w') as f:
                                        json.dump(last_ids, f)

                except Exception as e:
                    print(f"Error processing channel {channel_input}: {e}")
                    continue

            if messages_processed == 0:
                print("No new messages found.")
            else:
                print(f"Total messages processed: {messages_processed}")
            
            # چک کردن زمان باقی‌مانده قبل از sleep
            remaining_time = MAX_RUNTIME - (time.time() - start_time)
            if remaining_time < 30:
                print("Not enough time for next cycle, exiting...")
                break
            
            # استراحت 30 ثانیه
            print("Waiting 30 seconds...")
            await asyncio.sleep(30)
        
        # ذخیره نهایی state
        with open(STATE_FILE, 'w') as f:
            json.dump(last_ids, f)
        print(f"Final state saved to {STATE_FILE}")
        
        total_runtime = int(time.time() - start_time)
        print(f"Total runtime: {total_runtime} seconds")

    # تریگر کردن اجرای بعدی (خارج از async context)
    trigger_next_run()

if __name__ == "__main__":
    asyncio.run(main())
