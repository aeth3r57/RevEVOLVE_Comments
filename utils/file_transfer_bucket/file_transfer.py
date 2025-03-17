import boto3
from botocore.exceptions import NoCredentialsError
import os


def upload_to_s3(local_file_path, s3_file_name):
    bucket_name = os.environ['AWS_BUCKET_NAME']
    access_key_id = os.environ['AWS_ACCESS_KEY_ID']
    secret_access_key = os.environ['AWS_SECRET_ACCESS_KEY']
    acl = 'public-read'

    print(f"{local_file_path} file uploading into bucket.")
    # Create an S3 client with explicit credentials
    s3 = boto3.client('s3', aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key)

    try:
        # Upload the file
        s3.upload_file(local_file_path, bucket_name, s3_file_name, ExtraArgs={'ACL': acl, 'ContentType': 'text/plain'})
        print(f'Successfully uploaded {local_file_path} to {bucket_name}/{s3_file_name}')
    except NoCredentialsError:
        print('Credentials not available or not valid.')
