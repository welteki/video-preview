# OpenFaaS function to generate video previews.

OpenFaaS function to generate a video preview by sampling fragments from an input video and stitching them back together.

With the video-preview function you can generate a video preview like the one on the [OpenFaaS home page](https://www.openfaas.com/).


## Get started

The function accepts a download url for a video as inputs and will upload the resulting video to an S3 bucket.

Before you deploy the function create an S3 bucket that can be used to upload the generated videos.

**Secrets**

Create the required secrets to access S3:

```bash
export OPENFAAS_URL="https://openfaas.example.com"

faas-cli secret create video-preview-s3-key \
  --from-file .secrets/video-preview-s3-key

faas-cli secret create video-preview-s3-secret \
  --from-file .secrets/video-preview-s3-secret
```

**Environment variables**

Copy `example.s3_config.yaml` to `s3_config.yaml` and edit the values.

* `s3_bucket` - S3 bucket used to upload the output video
* `s3_endpoint_url` - The S3 endpoint url (can be left empty when using AWS S3)
* `s3_output_prefix` - Prefix to add the the output S3 key for the generated video. By default the name of the input video is used. Use this parameter to add a prefix the the video name.
* `debug` - If set to true the output of ffmpeg commands used to process the video will be included in the function logs. 

Deploy the function:

```bash
faas-cli deploy
```

## Generating a preview video

Example request payload to generate a preview video:

```json
{
    "url": "https://video-preview.fr-par-1.linodeobjects.com/input/openfaas-homepage-vid.webm",
    "samples": 4,
    "sample_duration": 2,
}
```

* `url` - Download url for the source video.
* `samples` - The number of samples to take from the source video.
* `sample_duration` - The duration of each sample.

In this case the output video will be 8 seconds long, 4 samples of 2 seconds each. By default samples are taken at timestamps evenly spread out over the video.

## Custom samples

Instead of taking samples evenly spread over the video you can use `sample_seconds` to set the timestamps at which a sample should be taken.

```json
{
    "url": "https://video-preview.fr-par-1.linodeobjects.com/input/openfaas-homepage-vid.webm",
    "sample_duration": 2,
    "sample_seconds": ["10", "30", "120", "270", "390", "420", "450", "480", "510", "570"]
}
```

## Resize the output video

By default the generated video will have the same size as the input video. You can change this by setting the `scale` parameter to specify an output size.

```json
{
    "url": "https://video-preview.fr-par-1.linodeobjects.com/input/openfaas-homepage-vid.webm",
    "samples": 4,
    "sample_duration": 2,
    "scale": "900:540"
}
```

## Select the output format

By default the output video will always be in `mp4` format. Set the `format` parameter in the request to select an other output format. 

```json
{
    "url": "https://video-preview.fr-par-1.linodeobjects.com/input/openfaas-homepage-vid.webm",
    "samples": 4,
    "sample_duration": 2,
    "format": "webm"
}
```