from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, filters
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

# Import du fichier "Explaination" qui permet de prévenir si la photo n'a pas été correctement importée
IMG_PATH = "/app/assets/explaination.png"


load_dotenv()  # Charge les variables depuis le .env

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
IMMICH_API_URL = os.getenv("IMMICH_API_URL")
IMMICH_API_KEY = os.getenv("IMMICH_API_KEY")
IMMICH_ALBUM_ID = os.getenv("IMMICH_ALBUM_ID")

HEADERS = {
    'Accept': 'application/json',
    "x-api-key": IMMICH_API_KEY
}
headers1 = {
    'x-api-key': IMMICH_API_KEY, 
  'Content-Type': 'application/json',
  'Accept': 'application/json'
}

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(stream=open(1, "w", encoding="utf-8", closefd=False)),
    ]
)

logger = logging.getLogger(__name__)

# === Fonction pour uploader une image vers Immich ===
def upload_to_immich(file_path: str):
    try:
        with open(file_path, 'rb') as f:
            stats = os.stat(file_path)
            files = {'assetData': f}
            data = {
                "albumId": IMMICH_ALBUM_ID,
                'deviceAssetId': f'{f}-{stats.st_mtime}',
                'deviceId': 'Telegram',
                'fileCreatedAt': datetime.fromtimestamp(stats.st_mtime),
                'fileModifiedAt': datetime.fromtimestamp(stats.st_mtime),
                'isFavorite': 'false',
            }
            response = requests.post(f"{IMMICH_API_URL}/assets", headers=HEADERS, files=files, data=data)
            idAsset = response.json().get('id')
            payload = json.dumps({ "ids": [idAsset] })

            response_album = requests.put(f"{IMMICH_API_URL}/albums/{IMMICH_ALBUM_ID}/assets", headers=headers1, data=payload)

        if response.status_code == 201:
            logger.info(f"✅ Image envoyée : {os.path.basename(file_path)}")
            logger.debug(f"Réponse JSON de l'upload : {response.json()}")
            logger.debug(f"Réponse JSON de l'ajout à l'album : {response_album.text}")
        else:
            logger.error(f"❌ Échec de l'envoi : {response.status_code} - {response.text}")

    except Exception as e:
        logger.exception(f"🚨 Erreur lors de l'envoi de l'image : {file_path} - {e}")

# === Handler des photos Telegram ===
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = update.message.photo[-1]
    file = await photo.get_file()
    file_path = os.path.join(tempfile.gettempdir(), f"{file.file_id}.jpg")

    await file.download_to_drive(file_path)
    
    size = os.path.getsize(file_path)  # ← Taille du fichier en octets

    upload_to_immich(file_path)
    os.remove(file_path)
    
    if size < 1_048_576:  # Moins de 1 Mo
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(IMG_PATH, 'rb'),
            caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
            parse_mode='Markdown'
        )

# === Handler des vidéos Telegram ===
async def video_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    file = await video.get_file()
    ext = os.path.splitext(doc.file_name)[-1]
    file_path = os.path.join(tempfile.gettempdir(), f"{file.file_id}{ext}")

    await file.download_to_drive(file_path)

    size = os.path.getsize(file_path)  # ← Taille du fichier en octets

    upload_to_immich(file_path)
    os.remove(file_path)


# === Handler des documents image ===
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.mime_type.startswith("image/") | doc.mime_type.startswith("video/") :
        return

    file = await doc.get_file()
    ext = os.path.splitext(doc.file_name)[-1]
    file_path = os.path.join(tempfile.gettempdir(), f"{doc.file_id}{ext}")

    await file.download_to_drive(file_path)
    
    size = os.path.getsize(file_path)  # ← Taille du fichier

    upload_to_immich(file_path)
    os.remove(file_path)
    
    if size < 1_048_576:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(IMG_PATH, 'rb'),
            caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
            parse_mode='Markdown'
        )

# === Lancement de l'application synchronisée ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()


    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.VIDEO, video_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE | filters.Document.VIDEO, document_handler))
    logger.info("🤖 Bot actif, en attente de photos…")
    print("🤖 Bot actif, en attente de photos…")
    app.run_polling()