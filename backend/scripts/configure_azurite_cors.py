"""One-time local setup: Azurite has no CORS rules by default, so a browser PUT-ing a
photo directly to a SAS blob URL (as the frontend does) gets blocked with
CorsPreflightFailure. Real Azure Storage needs the same treatment in Phase 3, via Bicep
instead of this script.

Run once after starting Azurite (`docker compose up -d azurite`), from backend/:
    python scripts/configure_azurite_cors.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from azure.storage.blob import BlobServiceClient, CorsRule  # noqa: E402

from shared import config  # noqa: E402


def main() -> None:
    client = BlobServiceClient.from_connection_string(config.azure_storage_connection_string())
    cors_rule = CorsRule(
        allowed_origins=["*"],
        allowed_methods=["GET", "PUT", "POST", "OPTIONS"],
        allowed_headers=["*"],
        exposed_headers=["*"],
        max_age_in_seconds=3600,
    )
    client.set_service_properties(cors=[cors_rule])
    print("Azurite blob service CORS configured for local dev (all origins).")


if __name__ == "__main__":
    main()
