# import asyncio
import os

import pytest
from pytest_docker_tools import container, fetch
# from pytest_docker_tools.wrappers.container import Container


redis_image = fetch(repository='redis:latest')
redis_container = container(image='{redis_image.id}', ports={'6379/tcp': None}, scope='session')

# rabbitmq_image = fetch(repository='rabbitmq:3-management')
# rabbitmq_container = container(image='{rabbitmq_image.id}', ports={'5672/tcp': None}, scope='function')


@pytest.fixture(scope='session')
def resource_dir():
    root_dir = os.path.dirname(os.path.dirname(__file__))
    return os.path.join(root_dir, 'resources')


@pytest.fixture
def resource(resource_dir):
    def _f(filename: str) -> str:
        return os.path.join(resource_dir, filename)
    return _f


@pytest.fixture
def get_resource(resource):
    def _f(filename: str) -> bytes:
        return open(resource(filename), 'rb').read()
    return _f
