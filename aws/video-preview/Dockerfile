FROM nixery.dev/shell/wget/gnutar/xz as ffmpeg

RUN wget https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-6.0.1-amd64-static.tar.xz
    # && wget https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-6.0.1-amd64-static.tar.xz.md5

# RUN md5sum -c ffmpeg-6.0.1-amd64-static.tar.xz.md5
RUN tar xvf ffmpeg-6.0.1-amd64-static.tar.xz

RUN mkdir -p ffmpeg/bin
RUN cp ffmpeg-*-amd64-static/ffmpeg ffmpeg/bin
RUN cp ffmpeg-*-amd64-static/ffprobe ffmpeg/bin

FROM public.ecr.aws/lambda/python:3.11

COPY --from=ffmpeg ffmpeg/bin /bin

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the specified packages
RUN pip install -r requirements.txt

# Copy function handler and modules
COPY video_preview ${LAMBDA_TASK_ROOT}/video_preview

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "video_preview.lambda_function.handler" ]