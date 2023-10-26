import os
import logging
import tempfile
import urllib
import ffmpeg
import boto3

from .preview import generate_video_preview, calculate_sample_seconds

s3_client = boto3.client('s3')

samples = os.getenv("samples", 4)
sample_duration = os.getenv("sample_duration", 2)
scale = os.getenv("scale")
format = os.getenv("format", "mp4")

s3_output_prefix = os.getenv("s3_output_prefix", "output")
debug = os.getenv("debug", "false").lower() == "true"

def handler(event, context):
    s3_bucket_name = event['Records'][0]['s3']['bucket']['name']

    key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')

    file_name, _ = os.path.basename(key).split(".")
    output_key = os.path.join(s3_output_prefix, file_name + "." + format)
    out_file = tempfile.NamedTemporaryFile(delete=True)

    try:
        input_url = s3_client.generate_presigned_url('get_object', Params={'Bucket': s3_bucket_name, 'Key': key}, ExpiresIn=60 * 60)
    except Exception as e:
        logging.error("failed to get presigned video url")
        raise e

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