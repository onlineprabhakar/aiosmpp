import asyncio
from pytest_docker_tools import container, fetch
from pytest_docker_tools.wrappers.container import Container


def _new_get_open_tcp_ports(self):
    ''' Gets all TCP sockets in the LISTEN state '''
    netstat = self._container.exec_run('cat /proc/net/tcp /proc/net/tcp6')[1].decode('utf-8').strip()

    ports = []
    for line in netstat.split('\n'):
        # Not interested in empty lines
        if not line:
            continue

        line = line.split()

        # Only interested in listen sockets
        if line[3] != '0A':
            continue

        ports.append(str(int(line[1].split(':', 1)[1], 16)))

    return ports

# Monkeypatch until https://github.com/Jc2k/pytest-docker-tools/issues/2
Container.get_open_tcp_ports = _new_get_open_tcp_ports


import pytest
import logging
from examples.server.send_delivery_notifications import DLRSMPPServer

redis_image = fetch(repository='redis:latest')
redis_container = container(image='{redis_image.id}', ports={'6379/tcp': None}, scope='session')

rabbitmq_image = fetch(repository='rabbitmq:3-management')
rabbitmq_container = container(image='{rabbitmq_image.id}', ports={'5672/tcp': None}, scope='function')
