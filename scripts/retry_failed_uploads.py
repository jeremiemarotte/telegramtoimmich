"""
Retente l'upload vers Immich des fichiers mis en quarantaine par le bot
(dossier FAILED_UPLOADS_DIR, voir bot/main.py) suite à un échec d'upload
(Immich injoignable, erreur de validation, etc.).

Usage :
  python scripts/retry_failed_uploads.py
"""

import os
import sys
import json
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bot"))

from main import upload_to_immich, get_user_config, FAILED_UPLOADS_DIR  # noqa: E402


def main() -> None:
    manifests = sorted(glob.glob(os.path.join(FAILED_UPLOADS_DIR, "*.json")))
    if not manifests:
        print("Aucun fichier en quarantaine.")
        return

    print(f"{len(manifests)} fichier(s) en quarantaine trouvé(s).\n")
    retried = failed = 0
    for manifest_path in manifests:
        file_path = manifest_path[: -len(".json")]
        if not os.path.exists(file_path):
            print(f"  ⚠️  {os.path.basename(file_path)} manquant, manifest ignoré.")
            continue

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        config = get_user_config(manifest["user_id"])
        print(f"Retry {os.path.basename(file_path)} ({manifest.get('username', '?')})…")
        if upload_to_immich(file_path, config["api_key"], config["album_id"]):
            print("  ✅ Envoyé.")
            os.remove(file_path)
            os.remove(manifest_path)
            retried += 1
        else:
            print("  ❌ Toujours en échec, laissé en quarantaine.")
            failed += 1

    print(f"\nTotal : {retried} envoyé(s), {failed} toujours en échec.")


if __name__ == "__main__":
    main()
