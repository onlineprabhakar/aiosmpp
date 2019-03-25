#!/bin/sh

service="$1"

if [ -z "${service}" ]; then
    echo "Service parameter missing"
    exit 1
fi

case "${service}" in
smppserver)
    echo "Running SMPP Server"
    exec /usr/binpython3 "${@:2}"
    ;;
*)
    echo "Unknown argument"
    exit 1
    ;;
esac
