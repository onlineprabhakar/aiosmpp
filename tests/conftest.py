import asyncio
from pytest_docker_tools import container, fetch
from pytest_docker_tools.wrappers.container import Container

import pytest
import logging
from examples.server.send_delivery_notifications import DLRSMPPServer

redis_image = fetch(repository='redis:latest')
redis_container = container(image='{redis_image.id}', ports={'6379/tcp': None}, scope='session')

rabbitmq_image = fetch(repository='rabbitmq:3-management')
rabbitmq_container = container(image='{rabbitmq_image.id}', ports={'5672/tcp': None}, scope='function')
