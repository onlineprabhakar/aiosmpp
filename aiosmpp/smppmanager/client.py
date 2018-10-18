import asyncio
import datetime
from typing import Dict, Any, Union

import aiohttp


# /api/v1/smpp/connections


class SMPPManagerClient(object):
    def __init__(self, host, ssl=None, timeout=0.5):
        self.host = host
        self.ssl = ssl
        self.timeout = timeout

        if ssl:
            self.url = 'https://' + host
        else:
            self.url = 'http://' + host

        self.session = None

        self.connectors = {'connectors': {}}

    def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self.session

    async def close(self):
        try:
            await self.session.close()
        except:
            pass

    async def get_connectors(self) -> Union[Dict[str, Any], None]:
        url = self.url + '/api/v1/smpp/connectors'

        try:
            async with self.get_session().get(url) as resp:
                json_data = await resp.json()
            # {'connectors': {}}
            return json_data
        except asyncio.TimeoutError:
            pass
        except Exception as err:
            print('get connectors err: {0}'.format(err))

        return None

    async def run(self, interval: int=120):
        while True:
            try:
                connector_data = await self.get_connectors()
                if not connector_data:
                    print('failed to get connector data')
                else:
                    print('Updated SMPP connector data')
                    self.connectors['connectors'].clear()
                    self.connectors.update(connector_data)
                    self.connectors['last_updated'] = datetime.datetime.now()

                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as err:
                print('get connectors loop err: {0}'.format(err))

