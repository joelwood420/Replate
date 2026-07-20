from azure.storage.blob import BlobServiceClient
from azure.storage.queue import QueueServiceClient

CONN_STR = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    "QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;"
)

# --- Blob ---
blob_service = BlobServiceClient.from_connection_string(CONN_STR)
container = blob_service.get_container_client("uploads")
if not container.exists():
    container.create_container()

blob_client = container.get_blob_client("test.txt")
blob_client.upload_blob(b"hello from local dev", overwrite=True)
print("Blob uploaded:", blob_client.url)

# --- Queue ---
queue_service = QueueServiceClient.from_connection_string(CONN_STR)
queue_client = queue_service.get_queue_client("jobs")
try:
    queue_client.create_queue()
except Exception:
    pass  # already exists

queue_client.send_message("test job message")
print("Queue message sent")

# read it back
messages = queue_client.receive_messages()
for msg in messages:
    print("Received:", msg.content)
    queue_client.delete_message(msg)