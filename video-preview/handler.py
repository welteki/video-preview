import os
import json
import logging
import tempfile
from urllib.parse import urlparse
import ffmpeg

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3Client = None
s3_endpoint_url = os.getenv("s3_endpoint_url")
s3_output_prefix = os.getenv("s3_output_prefix", "")
debug = os.getenv("debug", "false").lower() == "true"

def initS3():
    with open('/var/openfaas/secrets/video-preview-s3-key', 'r') as s:
        s3Key = s.read()
    with open('/var/openfaas/secrets/video-preview-s3-secret', 'r') as s:
        s3Secret = s.read()

    session = boto3.Session(
        aws_access_key_id=s3Key,
        aws_secret_access_key=s3Secret,
    )
    
    return session.client('s3', config=Config(signature_version='s3v4'), endpoint_url=s3_endpoint_url)

def get_parts(in_file, sample_duration, sample_seconds=[]):
    parts = []
    for t in sample_seconds:
        stream = in_file.video.trim(start=t, duration=sample_duration).setpts('PTS-STARTPTS')
        parts.append(stream)

    return parts

def handle(event, context):
    global s3Client

    # Initialise an S3 client upon first invocation
    if s3Client == None:
        s3Client = initS3()
    bucket_name = os.getenv('s3_bucket')

    data = json.loads(event.body)

    input_url = data["url"]

    if input_url is None:
        return {
            "statusCode": 400,
            "body": "url is required"
        }
    
    samples = data.get("samples", 1)
    sample_duration = data.get("sample_duration")
    sample_seconds = data.get("sample_seconds", [])

    if sample_duration is None:
        return {
            "statusCode": 400,
            "body": "sample_duration is required"
        }
    
    if sample_duration <= 0:
        return {
            "statusCode": 400,
            "body": "sample_duration must be greater than 0"
        }
    
    if samples <= 0:
        return {
            "statusCode": 400,
            "body": "samples must be greater than 0"
        }
    
    # Calculate sample_seconds based on the video duration, sample_duration and number of samples
    # when it is not set in the request body.
    if not sample_seconds:
        try:
            probe = ffmpeg.probe(input_url)
        except ffmpeg.Error as e:
            logging.error(e.stderr)
            return {
                "statusCode": 500,
                "body": "Failed to get video info"
            }
    
        duration = float(probe["format"]["duration"])
        sample_spacing = duration / samples

        # Sample spacing must always be larger than sample length
        if sample_spacing < sample_duration:
            return {
                "statusCode": 400,
                "body": 'sample_duration should be shorter then: {}'.format(sample_spacing)
            }
    
        for i in range(samples):
            sample_seconds.append(sample_spacing * i)

    scale = data.get("scale")
    format = data.get("format", "mp4")

    file_name, _ = os.path.basename(input_url).split(".")
    output_key = os.path.join(s3_output_prefix, file_name + "." + format)
    
    # Generate video preview
    try:
        in_file = ffmpeg.input(input_url)
        out = tempfile.NamedTemporaryFile(delete=True)

        parts = get_parts(in_file, sample_duration=sample_duration, sample_seconds=sample_seconds)
        stream = ffmpeg.concat(*parts)

        if scale is not None:
            width, height = scale.split(':')
            stream = ffmpeg.filter(stream, 'scale', width=width, height=height, force_original_aspect_ratio='decrease')

        (
            ffmpeg
            .output(stream, out.name, format=format)
            .overwrite_output()
            .run(quiet=not debug)
        )
    except Exception as e:
        logging.error(e)
        return {
            "statusCode": 500,
            "body": "Failed to generate video preview"
        }

    # Upload video file to S3 bucket.
    try:
        s3Client.upload_file(out.name, bucket_name, output_key, ExtraArgs={'ACL': 'public-read'})
    except ClientError as e:
        logging.error(e)
        return {
            "statusCode": 500,
            "body": "Failed to upload video preview"
        }
    
    try:
       out_probe = ffmpeg.probe(out.name)
    except ffmpeg.Error as e:
        logging.error(e.stderr)

        return {
            "statusCode": 500,
            "body": "Failed to get video info"
        }

    s3_endpoint = urlparse(s3_endpoint_url)

    return {
        "statusCode": 200,
        "body": {
            "url": 'https://{}.{}/{}'.format(bucket_name, s3_endpoint.hostname, output_key),
            "duration": out_probe["format"]["duration"],
            "size": out_probe["format"]["size"],
        }
    }
