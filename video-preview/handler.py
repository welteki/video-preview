import os
import json
import logging
import tempfile
import ffmpeg
import boto3
from botocore.config import Config

from .preview import generate_video_preview, calculate_sample_seconds

s3_client = None

samples = os.getenv("samples", 4)
sample_duration = os.getenv("sample_duration", 2)
scale = os.getenv("scale")
format = os.getenv("format", "mp4")

s3_output_prefix = os.getenv("s3_output_prefix", "output")
s3_bucket_name = os.getenv('s3_bucket')
debug = os.getenv("debug", "false").lower() == "true"

def handle(event, context):
    global s3_client, s3_endpoint

    # Initialise an S3 client upon first invocation
    if s3_client == None:
        s3_client = init_s3()

    data = json.loads(event.body)
    input_url = data["url"]

    file_name, _ = os.path.basename(input_url).split(".")
    output_key = os.path.join(s3_output_prefix, file_name + "." + format)
    out_file = tempfile.NamedTemporaryFile(delete=True)

    try:
        probe = ffmpeg.probe(input_url)
        video_duration = float(probe["format"]["duration"])
    except ffmpeg.Error as e:
        logging.error("failed to get video info")
        logging.error(e.stderr)
        raise e

    # Calculate sample_seconds based on the video duration, sample_duration and number of samples
    sample_seconds = calculate_sample_seconds(video_duration, samples, sample_duration)

    # Generate video preview
    try:
        generate_video_preview(input_url, out_file.name, sample_duration, sample_seconds, scale, format, quiet=not debug)
    except Exception as e:
        logging.error("failed to generate video preview")
        raise e

    # Upload video file to S3 bucket.
    try:
        s3_client.upload_file(out_file.name, s3_bucket_name, output_key, ExtraArgs={'ACL': 'public-read'})
    except Exception as e:
        logging.error("failed to upload video preview")
        raise e

def init_s3():
    with open('/var/openfaas/secrets/video-preview-s3-key', 'r') as s:
        s3Key = s.read()
    with open('/var/openfaas/secrets/video-preview-s3-secret', 'r') as s:
        s3Secret = s.read()

    session = boto3.Session(
        aws_access_key_id=s3Key,
        aws_secret_access_key=s3Secret,
    )

    s3_endpoint_url = os.getenv("s3_endpoint_url")
    
    return session.client('s3', config=Config(signature_version='s3v4'), endpoint_url=s3_endpoint_url)