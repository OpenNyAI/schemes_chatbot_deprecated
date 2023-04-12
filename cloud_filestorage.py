import os

from google.cloud import storage
from google.oauth2 import service_account

credentials = service_account.Credentials.from_service_account_file(os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'))
client = storage.Client(credentials=credentials)


async def upload_file_and_get_public_url(filename, phone_number, remote_filename):
    name, file_extension = os.path.splitext(filename)

    content_type = {'.gif': 'image/gif',
                    '.jpg': 'image/jpg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.PNG': 'image/png',
                    '.pdf': 'application/pdf',
                    '.ogg': 'audio/ogg',
                    '.mp3': 'audio/mpeg'}

    bucket = client.get_bucket(os.getenv('BUCKET_NAME'))
    blob = bucket.blob(os.path.join(f'chatbot/media_files/{phone_number}', remote_filename))
    blob.upload_from_filename(filename, content_type=content_type[file_extension])
    blob.make_public()
    return blob.public_url
