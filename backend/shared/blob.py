import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

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


def _blob_name_from_url(blob_url: str) -> str:
    container = config.blob_container_uploads()
    prefix = f"/{container}/"
    path = urlparse(blob_url).path
    if prefix not in path:
        raise ValueError(f"blob_url {blob_url!r} does not reference the {container!r} container")
    return path.split(prefix, 1)[1]


def blob_exists(blob_url: str) -> bool:
    """Whether the client has actually uploaded to a blob URL we handed out.

    generate_upload_sas_url only reserves a name - the blob itself does not exist
    until the client PUTs to it, and it may never do so if the upload fails or the
    app is closed mid-upload.
    """
    blob_client = _service_client().get_blob_client(
        container=config.blob_container_uploads(), blob=_blob_name_from_url(blob_url)
    )
    return blob_client.exists()


def generate_read_sas_url(blob_url: str) -> str:
    """Mint a short-lived read-only SAS URL for a blob previously returned by
    generate_upload_sas_url. The upload SAS is write-only, so a stored
    ImageBlobUrl is not itself browser-readable without this.
    """
    container = config.blob_container_uploads()
    blob_name = _blob_name_from_url(blob_url)

    service_client = _service_client()
    account_name = service_client.account_name
    account_key = service_client.credential.account_key

    expiry = datetime.now(timezone.utc) + timedelta(minutes=config.sas_token_expiry_minutes())
    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=expiry,
    )

    blob_client = service_client.get_blob_client(container=container, blob=blob_name)
    return f"{blob_client.url}?{sas_token}"
