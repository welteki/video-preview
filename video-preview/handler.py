import os
import json
import logging
import tempfile
from urllib.parse import urlparse
import ffmpeg

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3_client = None
s3_endpoint = None

s3_output_prefix = os.getenv("s3_output_prefix", "")
s3_bucket_name = os.getenv('s3_bucket')
debug = os.getenv("debug", "false").lower() == "true"

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

def sample_video(in_file, sample_duration, sample_seconds=[]):
    samples = []
    for t in sample_seconds:
        stream = in_file.video.trim(start=t, duration=sample_duration).setpts('PTS-STARTPTS')
        samples.append(stream)

    return samples

def generate_video_preview(in_filename, out_filename, sample_duration, sample_seconds, scale, format, quiet):
    in_file = ffmpeg.input(in_filename)

    samples = sample_video(in_file, sample_duration=sample_duration, sample_seconds=sample_seconds)
    stream = ffmpeg.concat(*samples)

    if scale is not None:
        width, height = scale.split(':')
        stream = ffmpeg.filter(stream, 'scale', width=width, height=height, force_original_aspect_ratio='decrease')

    (
        ffmpeg
        .output(stream, out_filename, format=format)
        .overwrite_output()
        .run(quiet=quiet)
    )

# Calculate sample_seconds based on the video duration, sample_duration and number of samples
def calculate_sample_seconds(duration, samples, sample_duration):
    sample_seconds = []
    sample_spacing = duration / samples

    # Sample spacing must always be larger than sample length
    if sample_spacing < sample_duration:
        raise Exception('sample_duration should be shorter then: {}'.format(sample_spacing))

    for i in range(samples):
        sample_seconds.append(sample_spacing * i)

    return sample_seconds

def parse_request(request_data):
    input_url = request_data["url"]
    if input_url is None:
        return None, 400, "url is required"

    samples = request_data.get("samples", 1)
    sample_duration = request_data.get("sample_duration")
    sample_seconds = request_data.get("sample_seconds", [])

    if sample_duration is None:
        return None, 400, "sample_duration is required"
    
    if sample_duration <= 0:
        return 400, "sample_duration must be greater than 0"
    
    if samples <= 0:
        return None, 400, "samples must be greater than 0"
    
    # Calculate sample_seconds when it is not set in the request body.
    if not sample_seconds:
        try:
            probe = ffmpeg.probe(input_url)
        except ffmpeg.Error as e:
            logging.error(e.stderr)
            return None, 500, "failed to get video info"

        try:
            duration = float(probe["format"]["duration"])
            sample_seconds = calculate_sample_seconds(duration, samples, sample_duration)
        except Exception as e:
            return None, 400, e.message
    
    scale = request_data.get("scale")
    format = request_data.get("format", "mp4")

    return {
        "input_url": input_url,
        "samples": samples,
        "sample_duration": sample_duration,
        "sample_seconds": sample_seconds,
        "scale": scale,
        "format": format,
    }, None, None

def handle(event, context):
    global s3_client, s3_endpoint

    # Initialise an S3 client upon first invocation
    if s3_client == None:
        s3_client = init_s3()
        s3_endpoint = urlparse(s3_client.meta.endpoint_url)

    request_data = json.loads(event.body)

    data, status_code, message = parse_request(request_data)
    if data is None:
        return {
            "statusCode": status_code,
            "body": message
        }

    input_url = data["input_url"]
    sample_duration = data["sample_duration"]
    sample_seconds = data["sample_seconds"]
    scale = data["scale"]
    format = data["format"]

    file_name, _ = os.path.basename(input_url).split(".")
    output_key = os.path.join(s3_output_prefix, file_name + "." + format)
    out_file = tempfile.NamedTemporaryFile(delete=True)
    
    # Generate video preview
    try:
        generate_video_preview(input_url, out_file.name, sample_duration, sample_seconds, scale, format, quiet=not debug)
    except Exception as e:
        logging.error(e)
        return {
            "statusCode": 500,
            "body": "failed to generate video preview"
        }

    # Upload video file to S3 bucket.
    try:
        s3_client.upload_file(out_file.name, s3_bucket_name, output_key, ExtraArgs={'ACL': 'public-read'})
    except ClientError as e:
        logging.error(e)
        return {
            "statusCode": 500,
            "body": "failed to upload video preview"
        }
    
    try:
       out_probe = ffmpeg.probe(out_file.name)
    except ffmpeg.Error as e:
        logging.error(e.stderr)

        return {
            "statusCode": 500,
            "body": "failed to get video info"
        }

    return {
        "statusCode": 200,
        "body": {
            "url": 'https://{}.{}/{}'.format(s3_bucket_name, s3_endpoint.hostname, output_key),
            "duration": out_probe["format"]["duration"],
            "size": out_probe["format"]["size"],
        }
    }
