import os
import json
import asyncio
import time
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# --- خواندن اطلاعات از متغیرهای محیطی (GitHub Secrets) ---
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
SESSION_STRING = os.environ.get("SESSION_STRING")
SOURCE_CHANNELS_STR = os.environ.get("SOURCE_CHANNELS")
DESTINATION_CHANNEL = int(os.environ.get("DESTINATION_CHANNEL"))

# --- تبدیل رشته کانال‌های مبدا به لیست ---
SOURCE_CHANNELS = []
for ch in SOURCE_CHANNELS_STR.split(','):
    ch = ch.strip()
    try:
        SOURCE_CHANNELS.append(int(ch))
    except ValueError:
        SOURCE_CHANNELS.append(ch)

STATE_FILE = 'last_message_ids.json'
MAX_RUNTIME = 9 * 60  # 9 دقیقه به ثانیه

async def main():
    start_time = time.time()
    
    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        print("Client created successfully.")
        print(f"Starting continuous monitoring for {MAX_RUNTIME} seconds...")

        try:
            with open(STATE_FILE, 'r') as f:
                last_ids = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            last_ids = {}

        # حلقه اصلی که مداوم اجرا میشه
        while True:
            current_time = time.time()
            
            # اگر بیشتر از 9 دقیقه گذشته، خروج
            if current_time - start_time > MAX_RUNTIME:
                print("Maximum runtime reached. Exiting...")
                break
            
            print(f"\n=== Checking for new messages (Runtime: {int(current_time - start_time)}s) ===")
            
            messages_processed = 0
            
            for channel_input in SOURCE_CHANNELS:
                try:
                    source_entity = await client.get_entity(channel_input)
                    str_source_id = str(source_entity.id)
                    
                    last_id = last_ids.get(str_source_id, 0)
                    newest_message_id = last_id

                    if last_id == 0:
                        # اولین بار - فقط آماده سازی
                        print(f"First time setup for channel: {getattr(source_entity, 'title', channel_input)}")
                        latest_message = await client.get_messages(source_entity, limit=1)
                        if latest_message:
                            newest_message_id = latest_message[0].id
                            last_ids[str_source_id] = newest_message_id
                            print(f"Set starting point to message ID: {newest_message_id}")
                    else:
                        # چک کردن پیام‌های جدید
                        messages_to_forward = []
                        async for message in client.iter_messages(source_entity, min_id=last_id, reverse=True):
                            messages_to_forward.append(message)
                            if message.id > newest_message_id:
                                newest_message_id = message.id
                        
                        if messages_to_forward:
                            print(f"Found {len(messages_to_forward)} new message(s) in {getattr(source_entity, 'title', channel_input)}")
                            
                            for message in messages_to_forward:
                                try:
                                    await client.send_message(DESTINATION_CHANNEL, message)
                                    print(f"✓ Forwarded message {message.id}")
                                    messages_processed += 1
                                    
                                    # فاصله کوتاه بین پیام‌ها
                                    await asyncio.sleep(1)
                                    
                                except Exception as e:
                                    print(f"✗ Failed to forward message {message.id}: {e}")
                            
                            last_ids[str_source_id] = newest_message_id
                            
                            # ذخیره state بعد از هر کانال
                            with open(STATE_FILE, 'w') as f:
                                json.dump(last_ids, f)

                except Exception as e:
                    print(f"Error processing channel {channel_input}: {e}")
                    continue

            if messages_processed == 0:
                print("No new messages found in any channel.")
            else:
                print(f"Total messages processed: {messages_processed}")
            
            # استراحت 30 ثانیه قبل از چک بعدی
            print("Waiting 30 seconds before next check...")
            await asyncio.sleep(30)
        
        # ذخیره نهایی state
        with open(STATE_FILE, 'w') as f:
            json.dump(last_ids, f)
        print(f"\nFinal state saved to {STATE_FILE}.")
        
        total_runtime = int(time.time() - start_time)
        print(f"Total runtime: {total_runtime} seconds")

if __name__ == "__main__":
    asyncio.run(main())
