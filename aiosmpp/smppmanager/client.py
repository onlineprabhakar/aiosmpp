import asyncio
import logging
import datetime
import os
from urllib.parse import urlparse
from typing import Dict, Any, Union, Optional

import aiohttp
import aioboto3
from botocore.config import Config

from aiosmpp.httpapi.routetable import MTRouteTable


class SMPPManagerClient(object):
    def __init__(self, url: str, region:str, route_table: MTRouteTable, timeout=0.5, logger: Optional[logging.Logger] = None):
        self.url = url
        self.region = region
        self.timeout = timeout
        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

        self._route_table = route_table

        self.session = None

    def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self.session

    async def close(self):
        try:
            await self.session.close()
        except:  # noqa: E722
            pass

    async def _get_connectors_normal_url(self) -> Union[Dict[str, Any], None]:
        url = self.url + '/api/v1/smpp/connectors'

        try:
            async with self.get_session().get(url) as resp:
                json_data = await resp.json()
            # {'connectors': {}}
            return json_data
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            raise
        except (ConnectionRefusedError, aiohttp.client_exceptions.ClientConnectorError):
            self.logger.error('Connection refused to {0}'.format(url))
        except Exception as err:
            self.logger.exception('get connectors err', exc_info=err)

        return None

    async def _get_connectors_ecs(self) -> Union[Dict[str, Any], None]:
        url = urlparse(self.url)
        cluster = url.netloc
        service = url.path.lstrip('/')

        result = None

        try:
            config = None
            if 'HTTPS_PROXY' in os.environ:
                config = Config(proxies={'HTTPS': os.environ['HTTPS_PROXY'].replace('https', 'http', 1)})

            self.logger.info('Getting tasks for {0}:{1}'.format(cluster, service))
            async with aioboto3.client('ecs', region_name=self.region, config=config) as ecs_client:

                resp = await ecs_client.list_tasks(cluster=cluster, serviceName=service, desiredStatus='RUNNING')
                task_arns = resp['taskArns']

                resp = await ecs_client.describe_tasks(cluster=cluster, tasks=task_arns)
                tasks = []

                for task in resp['tasks']:
                    # Bit ugly but will do for now
                    container = task['containers'][0]
                    container_instance = task['containerInstanceArn']
                    port = [bind for bind in container['networkBindings'] if bind['containerPort'] == 8081][0]['hostPort']

                    tasks.append((container_instance, port))

                # Tasks contain [(container instance arn, port), ...]
                container_instances = {}

                resp = await ecs_client.describe_container_instances(
                    cluster=cluster,
                    containerInstances=list(set([x[0] for x in tasks]))
                )
                for instance in resp.get('containerInstances', []):
                    container_instances[instance['ec2InstanceId']] = instance['containerInstanceArn']

            container_instance_to_ip = {}

            async with aioboto3.client('ec2', region_name=self.region, config=config) as ec2_client:
                resp = await ec2_client.describe_instances(InstanceIds=list(container_instances.keys()))

                for reservation in resp['Reservations']:
                    for instance in reservation['Instances']:
                        container_instance = container_instances[instance['InstanceId']]

                        container_instance_to_ip[container_instance] = instance['PrivateIpAddress']

            # So we've got the container instances that the tasks run on
            # We've converted the container instances to real instances
            # We've got a mapping of container instance 2 ip
            connectors = {}

            for container_instance_arn, port in tasks:
                ip = container_instance_to_ip[container_instance_arn]
                url = 'http://{0}:{1}/api/v1/smpp/connectors'.format(ip, port)

                try:
                    async with self.get_session().get(url) as resp:
                        json_data = await resp.json()
                    # {'connectors': {}}
                    self.logger.info('Hit ECS Url: {0} got {1}'.format(url, resp.status))
                    for connector, state in json_data.get('connectors', {}).items():
                        # Update if connection not in dict
                        if connector not in connectors:
                            connectors[connector] = state
                        # Update if connector in dict but not bound
                        elif not connectors[connector].startswith('BOUND'):
                            connectors[connector] = state

                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    raise
                except (ConnectionRefusedError, aiohttp.client_exceptions.ClientConnectorError):
                    self.logger.error('Connection refused to {0}'.format(url))
                except Exception as err:
                    self.logger.exception('get connectors err', exc_info=err)

            # Now we have connectors in connectors
            return {'connectors': connectors}

        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.logger.exception('get ecs connectors err', exc_info=err)

        return result

    async def get_connectors(self) -> Union[Dict[str, Any], None]:
        if self.url.startswith('ecs'):
            result = await self._get_connectors_ecs()
        else:
            result = await self._get_connectors_normal_url()

        return result

    async def run(self, interval: int = 120):
        while True:
            try:
                connector_data = await self.get_connectors()
                if not connector_data:
                    self.logger.warning('failed to get connector data')
                else:
                    self._route_table.update_connector_status(connector_data['connectors'])
                    self.logger.debug('Updated SMPP connector data')

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as err:
                self.logger.exception('get connectors loop', exc_info=err)

        await self.session.close()

        self.logger.info('Exiting run loop')
