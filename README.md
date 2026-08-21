# telegramToImmich
A bot that retrieves telegram pictures to store them on Immich albums.

Immich is a self-hosted cloud storage for pictures.

## 🧐 How does it works ?
When installed, the telegramBot checks each message. If your message contains a picture or a video, it will be uploaded to the immich albums set up.
To make sure you upload good quality pictures, we recommend to share "Files" and not "Pictures". That way, the pictures quality will not be reduced.

## 🛠️ How to install it ?

If you are using TrueNAS Scale as a NAS Service, you can use dockge to install the docker container.

To install the dokcer container :
1. Copy the [docker-compose.yml](docker-compose.yml) file
2. Define your env variables.

Here is a small guide to retrieve the env variables : 
- TELEGRAM_BOT_TOKEN: You must create a telegram bot first. To do so, discuss with @BotFather. You will be then given a token.
- TELEGRAM_API_ID / TELEGRAM_API_HASH: Required to run the self-hosted Telegram Bot API server (`telegram-bot-api` service in [docker-compose.yml](docker-compose.yml)), which lets the bot download files larger than the cloud API's 20 MB limit (up to 2 GB). Create them for free at https://my.telegram.org/apps.
- IMMICH_API_URL: It follows this format : http://YOUR-IMMICH-INSTANCE/api
- IMMICH_API_KEY: You can create an API key in the settings of your account.
- IMMICH_ALBUM_ID: You can retrieve the 
