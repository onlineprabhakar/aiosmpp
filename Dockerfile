FROM alpine:3.8

RUN apk add python3 gcc python3-dev musl-dev

RUN pip3 install aiohttp==3.5.4 aioboto3==6.2.2 aioredis==1.2.0 aioprometheus==18.7.1 aiohttp-sentry==0.5.0

ADD aiosmpp /app/aiosmpp
ADD resources/shim.sh /entrypoint
WORKDIR /app/

ENTRYPOINT ["/entrypoint"]