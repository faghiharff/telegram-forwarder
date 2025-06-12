import os
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
import json

# --- Load Environment Variables ---
API_ID = int(os.environ.get('TG_API_ID'))
API_HASH = os.environ.get('TG_API_HASH')
SESSION_FILE = os.environ.get('SESSION_FILE', 'session.session')
PHONE_NUMBER = os.environ.get('TG_PHONE') # برای لاگین اولیه
SOURCE_CHANNELS_RAW = os.environ.get('SOURCE_CHANNELS', '').split(',')
DESTINATION_CHANNEL_RAW = os.environ.get('DESTINATION_CHANNEL')

# تمیز کردن لیست کانال‌های مبدأ (حذف فضای خالی)
SOURCE_CHANNELS = [ch.strip() for ch in SOURCE_CHANNELS_RAW if ch.strip()]

client = TelegramClient(SESSION_FILE, API_ID, API_HASH)

# فایل برای نگهداری آیدی پیام‌های فوروارد شده
FORWARDED_MESSAGES_FILE = 'forwarded_messages.json'

def load_forwarded_messages():
    if os.path.exists(FORWARDED_MESSAGES_FILE):
        with open(FORWARDED_MESSAGES_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_forwarded_messages(data):
    with open(FORWARDED_MESSAGES_FILE, 'w') as f:
        json.dump(data, f)

async def get_channel_entity(client, channel_id_or_username):
    """
    Attempts to resolve a channel entity from its ID or username.
    Handles potential errors if the channel is not found.
    """
    try:
        if isinstance(channel_id_or_username, str) and channel_id_or_username.startswith('-100'):
            # It's likely a channel ID in string format
            return await client.get_entity(int(channel_id_or_username))
        return await client.get_entity(channel_id_or_username)
    except Exception as e:
        print(f"Error resolving entity for {channel_id_or_username}: {e}")
        return None

async def main():
    print("Connecting to Telegram...")
    await client.connect()

    if not await client.is_user_authorized():
        print("Client is not authorized. Starting authentication...")
        # اگر از قبل لاگین نشده‌اید، این بخش اجرا می‌شود
        try:
            await client.start(phone=PHONE_NUMBER)
        except Exception as e:
            print(f"Error during client start: {e}")
            print("Please ensure your phone number is correct and you've entered the code if prompted manually.")
            # In GitHub Actions, manual code entry is not possible.
            # The 'Generate Session' step in .github/workflows/main.yml should handle initial auth.
            return

    print("Client connected and authorized.")

    source_entities = {}
    for src in SOURCE_CHANNELS:
        entity = await get_channel_entity(client, src)
        if entity:
            source_entities[entity.id] = entity
            print(f"Monitoring source channel: {entity.title} (ID: {entity.id})")
        else:
            print(f"Warning: Could not resolve source channel: {src}")

    destination_entity = await get_channel_entity(client, DESTINATION_CHANNEL_RAW)
    if not destination_entity:
        print(f"Error: Could not resolve destination channel: {DESTINATION_CHANNEL_RAW}. Exiting.")
        return

    print(f"Destination channel: {destination_entity.title} (ID: {destination_entity.id})")

    # Load previously forwarded messages
    forwarded_messages_data = load_forwarded_messages()

    # Iterate through each source channel and fetch recent messages
    for src_id, src_entity in source_entities.items():
        print(f"Checking for new messages in {src_entity.title}...")
        last_forwarded_id = forwarded_messages_data.get(str(src_id), 0)
        messages_to_process = []

        try:
            # Fetch messages newer than the last forwarded message ID
            async for message in client.iter_messages(src_entity, min_id=last_forwarded_id):
                # Ensure the message is actually new and not the min_id itself if it was already forwarded
                if message.id > last_forwarded_id:
                    messages_to_process.append(message)

            # Sort messages by ID to ensure correct order of forwarding
            messages_to_process.sort(key=lambda m: m.id)

            if not messages_to_process:
                print(f"No new messages found in {src_entity.title} since ID {last_forwarded_id}.")
                continue

            print(f"Found {len(messages_to_process)} new messages in {src_entity.title}. Processing...")

            new_last_id = last_forwarded_id
            for message in messages_to_process:
                print(f"Processing message ID {message.id} from {src_entity.title}")
                try:
                    # Check if the message is a text message or has media
                    if message.text or message.media:
                        try:
                            # Attempt to forward directly
                            print(f"Attempting direct forward for message ID {message.id}...")
                            await client.forward_messages(destination_entity, message)
                            print(f"Successfully directly forwarded message ID {message.id}.")
                        except Exception as e_forward:
                            print(f"Direct forward failed for message ID {message.id} (Error: {e_forward}). Attempting to copy...")
                            # If direct forward fails, try to copy the message content
                            if message.media:
                                if isinstance(message.media, (MessageMediaPhoto, MessageMediaDocument)):
                                    # For photos and documents, send with file
                                    await client.send_file(
                                        destination_entity,
                                        message.media,
                                        caption=message.text,
                                        # attributes can be problematic, better to avoid if not needed
                                    )
                                elif isinstance(message.media, MessageMediaWebPage):
                                    # For web previews, send text with URL if available
                                    text_to_send = message.text or ""
                                    if message.media.url and message.media.url not in text_to_send:
                                        text_to_send += f"\n\n{message.media.url}"
                                    await client.send_message(destination_entity, text_to_send)
                                else:
                                    # Fallback for other media types (e.g., video, voice)
                                    # Try to send as message, might lose media content
                                    await client.send_message(destination_entity, message.text or f"Message with unsupported media type from {src_entity.title}")
                            else:
                                # For text-only messages (or messages with media that couldn't be handled by send_file)
                                await client.send_message(destination_entity, message.text)
                            print(f"Successfully copied message ID {message.id}.")
                    else:
                        print(f"Skipping empty message ID {message.id} from {src_entity.title}.")

                    new_last_id = max(new_last_id, message.id) # Update last processed ID
                except Exception as e_send:
                    print(f"Error sending/copying message ID {message.id} from {src_entity.title}: {e_send}")

            # Update the last forwarded message ID for this source channel
            forwarded_messages_data[str(src_id)] = new_last_id
            save_forwarded_messages(forwarded_messages_data)

        except Exception as e_channel:
            print(f"Error processing messages from {src_entity.title}: {e_channel}")

    await client.disconnect()
    print("Client disconnected.")

if __name__ == '__main__':
    asyncio.run(main())
