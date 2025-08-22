from pyrogram import Client, filters
from pyrogram.types import Message
from bot.helper.ext_utils.user_prefs import set_user_pref

@Client.on_message(filters.command("setleechmode") & filters.private)
def set_leech_mode(client: Client, message: Message):
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ["media", "document"]:
        message.reply("Usage: /setleechmode [media|document]")
        return
    set_user_pref(message.from_user.id, "leech_mode", args[1].lower())
    message.reply(f"Set leech upload mode to {args[1].lower()}.")

@Client.on_message(filters.command("setthumbnail") & filters.private)
def set_thumbnail(client: Client, message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        message.reply("Reply to a photo with /setthumbnail to set as thumbnail.")
        return
    file_id = message.reply_to_message.photo.file_id
    set_user_pref(message.from_user.id, "thumbnail", file_id)
    message.reply("Custom thumbnail set!")
