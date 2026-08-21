from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, CommandHandler, filters
)
from telegram.error import TelegramError
import logging
import requests
import os
from dotenv import load_dotenv
import json
import asyncio
import tempfile
from datetime import datetime, timezone
from pathlib import Path

load_dotenv()

IMG_PATH = "/app/assets/explaination.png"
FAILED_UPLOADS_DIR = os.getenv("FAILED_UPLOADS_DIR", os.path.join(tempfile.gettempdir(), "failed_uploads"))
os.makedirs(FAILED_UPLOADS_DIR, exist_ok=True)

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
        logging.FileHandler(os.path.join(tempfile.gettempdir(), "bot.log"), encoding="utf-8"),
        logging.StreamHandler(stream=open(1, "w", encoding="utf-8", closefd=False)),
    ]
)

logger = logging.getLogger(__name__)


def upload_to_immich(file_path: str, api_key: str, album_id: str) -> bool:
    """Envoie le fichier à Immich puis l'ajoute à l'album. Renvoie True si les deux étapes réussissent."""
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
                'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc).isoformat(),
                'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime, tz=timezone.utc).isoformat(),
                'isFavorite': 'false',
            }
            response = requests.post(f"{IMMICH_API_URL}/assets", headers=headers_upload, files=files, data=data, timeout=60)
    except requests.exceptions.RequestException as e:
        logger.error(f"🚨 Immich injoignable lors de l'upload de {os.path.basename(file_path)} : {e}")
        return False

    if response.status_code not in (200, 201):
        logger.error(
            f"❌ Échec de l'upload Immich ({response.status_code}) pour {os.path.basename(file_path)} : {response.text}"
        )
        return False

    body = response.json()
    id_asset = body.get('id')
    if response.status_code == 200:
        logger.info(f"↺ Déjà présent sur Immich (doublon détecté) : {os.path.basename(file_path)} (asset={id_asset})")
    else:
        logger.info(f"✅ Fichier envoyé à Immich : {os.path.basename(file_path)} (asset={id_asset})")

    try:
        response_album = requests.put(
            f"{IMMICH_API_URL}/albums/{album_id}/assets",
            headers=headers_album,
            data=json.dumps({"ids": [id_asset]}),
            timeout=30,
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"🚨 Immich injoignable lors de l'ajout à l'album {album_id} (asset={id_asset}) : {e}")
        return False

    if response_album.status_code != 200:
        logger.error(
            f"❌ Échec de l'ajout à l'album {album_id} (asset={id_asset}) : {response_album.status_code} - {response_album.text}"
        )
        return False

    logger.debug(f"Réponse album : {response_album.text}")
    return True


def _quarantine_failed_upload(file_path: str, user_id: int, username: str) -> None:
    """Déplace un fichier dont l'upload Immich a échoué vers FAILED_UPLOADS_DIR pour un retry ultérieur."""
    dest = os.path.join(FAILED_UPLOADS_DIR, os.path.basename(file_path))
    manifest = {
        "user_id": user_id,
        "username": username,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        os.replace(file_path, dest)
        with open(f"{dest}.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        logger.warning(f"📦 Fichier mis en quarantaine pour retry : {dest}")
    except OSError as e:
        logger.error(f"🚨 Impossible de mettre {file_path} en quarantaine : {e}")


async def _process_media(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    telegram_file,
    ext_fallback: str,
    check_quality: bool,
):
    """Télécharge un fichier Telegram puis l'envoie à Immich, avec un diagnostic distinct pour chaque étape."""
    user_id = update.message.from_user.id
    username = update.message.from_user.full_name
    config = get_user_config(user_id)

    try:
        file = await telegram_file.get_file()
    except TelegramError as e:
        logger.error(f"❌ getFile Telegram a échoué pour {username} (id={user_id}) : {e}")
        return

    ext = os.path.splitext(telegram_file.file_name)[-1] if getattr(telegram_file, "file_name", None) else ext_fallback
    file_path = os.path.join(tempfile.gettempdir(), f"{file.file_id}{ext}")

    try:
        await file.download_to_drive(file_path)
    except TelegramError as e:
        logger.error(f"❌ Téléchargement Telegram échoué pour {username} (id={user_id}) : {e}")
        return

    try:
        size = os.path.getsize(file_path)
        if not upload_to_immich(file_path, config["api_key"], config["album_id"]):
            _quarantine_failed_upload(file_path, user_id, username)
            return

        if check_quality and size < 1_048_576:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=open(IMG_PATH, 'rb'),
                caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
                parse_mode='Markdown',
            )
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.full_name
    logger.info(f"📷 Photo reçue de {username} (id={user_id})")

    photo = update.message.photo[-1]
    await _process_media(update, context, photo, ext_fallback=".jpg", check_quality=True)


async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.full_name
    logger.info(f"🎥 Vidéo reçue de {username} (id={user_id})")

    video = update.message.video
    await _process_media(update, context, video, ext_fallback=".mp4", check_quality=False)


async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.full_name

    doc = update.message.document
    if not (doc.mime_type.startswith("image/") or doc.mime_type.startswith("video/")):
        return
    logger.info(f"📎 Document ({doc.mime_type}) reçu de {username} (id={user_id})")

    is_image = doc.mime_type.startswith("image/")
    ext_fallback = ".jpg" if is_image else ".mp4"
    await _process_media(update, context, doc, ext_fallback=ext_fallback, check_quality=is_image)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Filet de sécurité pour toute exception non interceptée par les handlers."""
    logger.error(f"🚨 Exception non gérée pour l'update {update}", exc_info=context.error)


async def monid_handler(update: Update, _context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    await update.message.reply_text(
        f"Ton ID Telegram : `{user.id}`\nTon nom : {user.full_name}",
        parse_mode='Markdown',
    )


if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).read_timeout(60).write_timeout(60).connect_timeout(60).build()

    app.add_handler(CommandHandler("monid", monid_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VIDEO, video_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, document_handler))
    app.add_error_handler(error_handler)
    logger.info("🤖 Bot actif, en attente de photos…")
    app.run_polling()
