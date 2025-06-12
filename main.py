import os
import json
import asyncio
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

async def main():
    async with TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH) as client:
        print("Client created successfully.")

        try:
            with open(STATE_FILE, 'r') as f:
                last_ids = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            last_ids = {}

        for channel_input in SOURCE_CHANNELS:
            try:
                source_entity = await client.get_entity(channel_input)
                str_source_id = str(source_entity.id)
                
                print(f"\n---> Checking channel: {getattr(source_entity, 'title', channel_input)}")
                
                last_id = last_ids.get(str_source_id, 0)
                newest_message_id = last_id
                messages_to_process = []

                # #############################################################
                # ### شروع منطق اصلاح شده برای جلوگیری از ارسال پیام‌های قدیمی ###
                # #############################################################

                if last_id == 0:
                    # این کانال برای اولین بار پردازش می‌شود. فقط آخرین پیام را می‌گیریم.
                    print("First time processing this channel. Fetching only the very last message to set a starting point.")
                    latest_message = await client.get_messages(source_entity, limit=1)
                    if latest_message:
                        messages_to_process.append(latest_message[0])
                        newest_message_id = latest_message[0].id
                else:
                    # این کانال قبلا پردازش شده، پیام‌های جدیدتر را می‌گیریم.
                    async for message in client.iter_messages(source_entity, min_id=last_id, reverse=True):
                        messages_to_process.append(message)
                        if message.id > newest_message_id:
                            newest_message_id = message.id
                
                # ###########################################################
                # ### پایان منطق اصلاح شده                                  ###
                # ###########################################################

                if not messages_to_process:
                    print("No new messages.")
                    continue
                    
                print(f"Found {len(messages_to_process)} new message(s) to process.")

                for message in messages_to_process:
                    try:
                        await client.send_message(DESTINATION_CHANNEL, message)
                        print(f"Copied message {message.id} from {str_source_id}")
                    except Exception as e:
                        print(f"Could not copy message {message.id}. Error: {e}")
                    
                    await asyncio.sleep(2)

                last_ids[str_source_id] = newest_message_id
                print(f"Updated last ID for {str_source_id} to {newest_message_id}")

            except Exception as e:
                print(f"Error processing channel {channel_input}: {e}")
                continue

        with open(STATE_FILE, 'w') as f:
            json.dump(last_ids, f)
        print(f"\nState saved to {STATE_FILE}.")

if __name__ == "__main__":
    asyncio.run(main())
