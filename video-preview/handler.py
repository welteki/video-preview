import os
import json
import logging
import tempfile
import ffmpeg

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

s3Client = None

def initS3():
    with open('/var/openfaas/secrets/s3-key', 'r') as s:
        s3Key = s.read()
    with open('/var/openfaas/secrets/s3-secret', 'r') as s:
        s3Secret = s.read()

    session = boto3.Session(
        aws_access_key_id=s3Key,
        aws_secret_access_key=s3Secret,
    )
    
    return session.client('s3', config=Config(signature_version='s3v4'), endpoint_url="https://eu-central-1.linodeobjects.com")

def get_parts(in_file, trim=[], trim_duration=[]):
    parts = []
    if trim_duration:
        for v in trim_duration:
            start, duration = v.split(':')
            stream = in_file.video.trim(start=start, duration=duration).setpts('PTS-STARTPTS')
            parts.append(stream)
    elif trim:
        for v in trim:
            start, end = v.split(':')
            stream = in_file.video.trim(start=start, end=end).setpts('PTS-STARTPTS')
            parts.append(stream)

    return parts

def get_trim_duration(duration, samples, sample_length):
    sample_spacing = duration / samples

    # Sample spacing must always be larger than sample length
    if sample_spacing < sample_length:
        raise Exception('sample length should be shorter then: {}'.format(sample_spacing))

    trim_duration = []
    for i in range(samples):
        start = sample_spacing * i
        trim_duration.append(str(start) + ":" + str(sample_length))
    
    return trim_duration

def handle(event, context):
    global s3Client

    # Initialise an S3 client upon first invocation
    if s3Client == None:
        s3Client = initS3()
    bucket_name = os.getenv('s3_bucket')

    data = json.loads(event.body)

    trim = data.get("trim", [])
    trim_duration = data.get("trim_duration", [])

    scale = data.get("scale")

    samples = data.get("samples")
    sample_duration = data.get("sample_duration")

    format = data.get("format", "mp4")
    file_name, extension = os.path.basename(data["name"]).split(".")

    input_key = os.path.join('input', file_name + "." + extension)
    output_key = os.path.join('output', file_name + "." + format)
    
    input_url = s3Client.generate_presigned_url('get_object', Params={'Bucket': bucket_name, 'Key': input_key}, ExpiresIn=60 * 60)

    if not trim and not trim_duration:
        try:
            probe = ffmpeg.probe(input_url)
        except ffmpeg.Error as e:
            logging.error(e.stderr)
            return {
                "statusCode": 500,
                "body": "Failed to get video info"
            }
        
        duration = float(probe["format"]["duration"])
        trim_duration = get_trim_duration(duration, samples, sample_duration)

    # Generate video preview
    try:
        in_file = ffmpeg.input(input_url)
        out = tempfile.NamedTemporaryFile()

        parts = get_parts(in_file, trim, trim_duration)
        stream = ffmpeg.concat(*parts)

        if scale is not None:
            width, height = scale.split(':')
            stream = ffmpeg.filter(stream, 'scale', width=width, height=height, force_original_aspect_ratio='decrease')

        (
            ffmpeg
            .output(stream, out.name, format=format)
            .overwrite_output()
            .run()
        )
    except Exception as e:
        logging.error(e)
        return {
            "statusCode": 500,
            "body": "Failed to generate video preview"
        }


    # Upload video file to S3 bucket.
    try:
        s3Client.upload_file(out.name, bucket_name, output_key)
    except ClientError as e:
        logging.error(e)
        return {
            "statusCode": 500,
            "body": "Failed to upload video preview"
        }

    return {
        "statusCode": 200,
        "body": "Success"
    }
