from telegram import Update
from telegram.ext import (
    ApplicationBuilder, ContextTypes,
    MessageHandler, filters
)
import logging
import requests
import os
import json
import asyncio
from datetime import datetime

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
        logging.FileHandler("bot.log"),      # Log dans un fichier
        logging.StreamHandler()              # Log aussi dans la console
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
            response = requests.post(f"{IMMICH_URL}/assets", headers=HEADERS, files=files, data=data)
            idAsset = response.json().get('id')
            payload = json.dumps({ "ids": [idAsset] })

            response_album = requests.put(f"{IMMICH_URL}/albums/{IMMICH_ALBUM_ID}/assets", headers=headers1, data=payload)

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
    file_path = f"/tmp/{file.file_id}.jpg"

    await file.download_to_drive(file_path)
    upload_to_immich(file_path)
    os.remove(file_path)
    
    if size < 1_048_576:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open('/app/explaination.png', 'rb'),
            caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
            parse_mode='Markdown'
        )

# === Handler des documents image ===
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc.mime_type.startswith("image/"):
        return

    file = await doc.get_file()
    ext = os.path.splitext(doc.file_name)[-1]
    file_path = f"/tmp/{doc.file_id}{ext}"

    await file.download_to_drive(file_path)
    upload_to_immich(file_path)
    os.remove(file_path)
    
    if size < 1_048_576:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open('/app/explication.jpeg', 'rb'),
            caption='⚠️ La photo est de *mauvaise qualité*.\n Pense à la télécharger via *Fichier > Galerie*. 😉',
            parse_mode='Markdown'
        )

# === Lancement de l'application synchronisée ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.Document.IMAGE, document_handler))
    logger.info("🤖 Bot actif, en attente de photos…")
    print("🤖 Bot actif, en attente de photos…")
    app.run_polling()