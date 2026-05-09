from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, filters
)
import logging
import requests
import os
from dotenv import load_dotenv
import json
import asyncio
import tempfile
from datetime import datetime
from pathlib import Path

IMG_PATH = "/app/assets/explaination.png"

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IMMICH_API_URL = os.getenv("IMMICH_API_URL")

# Config par défaut (fallback si l'utilisateur n'est pas mappé)
DEFAULT_API_KEY = os.getenv("IMMICH_API_KEY")
DEFAULT_ALBUM_ID = os.getenv("IMMICH_ALBUM_ID")

# Construit le mapping telegram_id -> nom depuis TELEGRAM_USER_<NOM>=<telegram_id>
TELEGRAM_ID_TO_NAME: dict[str, str] = {}
for key, value in os.environ.items():
    if key.startswith("TELEGRAM_USER_"):
        name = key[len("TELEGRAM_USER_"):]
        TELEGRAM_ID_TO_NAME[value] = name

# Construit le mapping nom -> {api_key, album_id} depuis IMMICH_API_KEY_<NOM> et IMMICH_ALBUM_ID_<NOM>
USER_CONFIG: dict[str, dict] = {}
for key, value in os.environ.items():
    if key.startswith("IMMICH_API_KEY_"):
        name = key[len("IMMICH_API_KEY_"):]
        USER_CONFIG.setdefault(name, {})["api_key"] = value
    elif key.startswith("IMMICH_ALBUM_ID_"):
        name = key[len("IMMICH_ALBUM_ID_"):]
        USER_CONFIG.setdefault(name, {})["album_id"] = value


def get_user_config(telegram_user_id: int) -> dict:
    name = TELEGRAM_ID_TO_NAME.get(str(telegram_user_id))
    config = USER_CONFIG.get(name, {}) if name else {}
    return {
        "api_key": config.get("api_key", DEFAULT_API_KEY),
        "album_id": config.get("album_id", DEFAULT_ALBUM_ID),
    }


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(stream=open(1, "w", encoding="utf-8", closefd=False)),
    ]
)

logger = logging.getLogger(__name__)


def upload_to_immich(file_path: str, api_key: str, album_id: str):
    headers_upload = {
        'Accept': 'application/json',
        'x-api-key': api_key,
    }
    headers_album = {
        'x-api-key': api_key,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    try:
        with open(file_path, 'rb') as f:
            stats = os.stat(file_path)
            files = {'assetData': f}
            data = {
                'deviceAssetId': f'{file_path}-{stats.st_mtime}',
                'deviceId': 'Telegram',
                'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime),
                'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime),
                'isFavorite': 'false',
            }
            response = requests.post(f"{IMMICH_API_URL}/assets", headers=headers_upload, files=files, data=data)
            id_asset = response.json().get('id')
            payload = json.dumps({"ids": [id_asset]})
            response_album = requests.put(
                f"{IMMICH_API_URL}/albums/{album_id}/assets",
                headers=headers_album,
                data=payload,
            )

        if response.status_code == 201:
            logger.info(f"✅ Fichier envoyé : {os.path.basename(file_path)}")
            logger.debug(f"Réponse upload : {response.json()}")
            logger.debug(f"Réponse album : {response_album.text}")
        else:
            logger.error(f"❌ Échec de l'envoi : {response.status_code} - {response.text}")

    except Exception as e:
        logger.exception(f"🚨 Erreur lors de l'envoi : {file_path} - {e}")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    config = get_user_config(user_id)

    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(tempfile.gettempdir(), f"{file.file_id}.jpg")

    await file.download_to_drive(file_path)
    size = os.path.getsize(file_path)

    upload_to_immich(file_path, config["api_key"], config["album_id"])
    os.remove(file_path)

    if size < 1_048_576:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(IMG_PATH, 'rb'),
            caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
            parse_mode='Markdown',
        )


async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    config = get_user_config(user_id)

    video = update.message.video
    file = await video.get_file()
    ext = os.path.splitext(video.file_name)[-1] if video.file_name else ".mp4"
    file_path = os.path.join(tempfile.gettempdir(), f"{file.file_id}{ext}")

    await file.download_to_drive(file_path)

    upload_to_immich(file_path, config["api_key"], config["album_id"])
    os.remove(file_path)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    config = get_user_config(user_id)

    doc = update.message.document
    if not (doc.mime_type.startswith("image/") or doc.mime_type.startswith("video/")):
        return

    file = await doc.get_file()
    ext = os.path.splitext(doc.file_name)[-1]
    file_path = os.path.join(tempfile.gettempdir(), f"{doc.file_id}{ext}")

    await file.download_to_drive(file_path)
    size = os.path.getsize(file_path)

    upload_to_immich(file_path, config["api_key"], config["album_id"])
    os.remove(file_path)

    if size < 1_048_576:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(IMG_PATH, 'rb'),
            caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
            parse_mode='Markdown',
        )


async def monid_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    await update.message.reply_text(
        f"Ton ID Telegram : `{user.id}`\nTon nom : {user.full_name}",
        parse_mode='Markdown',
    )


if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("monid", monid_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VIDEO, video_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, document_handler))
    logger.info("🤖 Bot actif, en attente de photos…")
    app.run_polling()
