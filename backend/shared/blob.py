import uuid
from datetime import datetime, timedelta, timezone

from azure.storage.blob import BlobSasPermissions, BlobServiceClient, generate_blob_sas

from shared import config


def _service_client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(config.azure_storage_connection_string())


def generate_upload_sas_url(blob_name: str | None = None) -> dict:
    container = config.blob_container_uploads()
    blob_name = blob_name or f"{uuid.uuid4()}.jpg"

    service_client = _service_client()
    account_name = service_client.account_name
    account_key = service_client.credential.account_key

    container_client = service_client.get_container_client(container)
    if not container_client.exists():
        container_client.create_container()

    expiry = datetime.now(timezone.utc) + timedelta(minutes=config.sas_token_expiry_minutes())
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(write=True, create=True),
        expiry=expiry,
    )

    blob_client = service_client.get_blob_client(container=container, blob=blob_name)
    return {
        "blob_name": blob_name,
        "blob_url": blob_client.url,
        "sas_url": f"{blob_client.url}?{sas_token}",
        "expiry": expiry.isoformat(),
    }
