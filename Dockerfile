FROM alpine:3.8

RUN apk add python3

ADD aiosmpp /app/aiosmpp
ADD resources/shim.sh /entrypoint
WORKDIR /app/

RUN pip3 install aiohttp==3.5.4 aioboto3==6.2.2 aioredis==1.2.0

