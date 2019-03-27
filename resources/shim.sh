#!/bin/sh

service="$1"; shift

if [ -z "${service}" ]; then
    echo "\"service\" parameter missing"
    exit 1
fi

case "${service}" in
smppmanager)
    echo "Running SMPP Server"
    exec /usr/bin/python3 -m aiosmpp.smppmanager.server "${@}"
    ;;
httpapi)
    echo "Running HTTP Server"
    exec /usr/bin/python3 -m aiosmpp.httpapi.server "${@}"
    ;;
*)
    echo "Unknown argument"
    exit 1
    ;;
esac
