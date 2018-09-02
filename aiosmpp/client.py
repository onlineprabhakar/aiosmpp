import asyncio
import enum
from typing import Optional, Dict, Any, Callable
import async_timeout

from aiosmpp import pdu


class SMPPConnectionState(enum.Enum):
    OPEN = enum.auto()
    BOUND_TX = enum.auto()
    BOUND_RX = enum.auto()
    BOUND_TRX = enum.auto()
    CLOSED = enum.auto()


class SMPPClientProtocol(asyncio.Protocol):
    def __init__(self, config, loop: Optional[asyncio.AbstractEventLoop]=None):
        self.loop = loop
        self.smpp_min_verison = 0x34
        if not loop:
            self.loop = asyncio.get_event_loop()

        self.transport = None
        self.config: Dict[str, Any] = config
        self.state: SMPPConnectionState = SMPPConnectionState.CLOSED
        self.conn_lost_trigger: Callable[[], None] = lambda: None

        # enquire_link
        self.enquire_link_enabled = True
        self.enquire_link_timeout = 0.15  # 150ms
        self.enquire_link_period = 20
        self.enquire_link_future = None

        self._seq_number = 0x01
        self.pending_responses = {}  # Seq ID -> (timer coro, handler_func/partial)

        # Defaults
        self.username = 'testuser'
        self.password = 'testpw'
        self.system_type = None
        self.interface_version = 0x34
        self.addr_ton = 1
        self.addr_npi = 1

        self.bind_resp_timeout = 0.15  # 150ms

    def __del__(self):
        self.close()

    def close(self):
        self._close_session()

    def set_connection_lost_callback(self, func: Callable[[], None]):
        self.conn_lost_trigger = func

    def get_sequence_number(self) -> int:
        result = self._seq_number
        self._seq_number += 1

        return result

    def connection_made(self, transport: asyncio.Transport):
        self.transport = transport
        print('Connected to {0[0]}:{0[1]}'.format(self.transport.get_extra_info('peername')))
        self.state = SMPPConnectionState.OPEN

    def data_received(self, data: bytes):
        print('Data received: {0}'.format(data))

        if len(data) < 16:
            print('Recieved pkt len less than 16 bytes, invalid header')
            return

        hdr = pdu.decode_header(data)

        if hdr['seq_no'] in self.pending_responses:
            timeout_future, handler = self.pending_responses.pop(hdr['seq_no'])
            timeout_future.cancel()
            if handler:
                handler(hdr)
            return

        print('No req matching {0}'.format(hdr['seq_no']))

    def connection_lost(self, exc):
        print('Lost connection to {0[0]}:{0[1]}'.format(self.transport.get_extra_info('peername')))
        self.state = SMPPConnectionState.CLOSED

        self._close_session()

        # Trigger callback for connection lost
        self.conn_lost_trigger()

    def bind_trx(self):
        seq_no = self.get_sequence_number()
        pkt = pdu.bind_trx(
            sequence_number=seq_no,
            system_id=self.username,
            password=self.password,
            system_type=self.system_type,
            interface_version=self.interface_version,
            addr_ton=self.addr_ton,
            addr_npi=self.addr_npi,
            address_range=None
        )

        self.pending_responses[seq_no] = (
            asyncio.ensure_future(self.timeout_coro('bind_trx', self.bind_resp_timeout), loop=self.loop),
            self.bind_trx_resp
        )
        self.transport.write(pkt)
        print('Requested TRX bind')

    def bind_trx_resp(self, pkt: Dict[str, Any]):
        print('Got Bind TRX response {0}'.format(pkt))

        if pkt['status'] != pdu.Status.ESME_ROK:
            print('TRX Bind did not get ESME_ROK')
            self._close_session()
            return

        bind_resp = pdu.decode_bind_trx_resp(pkt['payload'])

        if 0x0210 in bind_resp['tlvs'] and bind_resp['tlvs'][0x0210] > self.smpp_min_verison:
            print('SMPP Server minimum version ({0}) is higher than ours, cant continue'.format(bind_resp['tlvs'][0x0210]))
            self._close_session()
            return

        self.state = SMPPConnectionState.BOUND_TRX
        print('TRX Bound')

        self.setup_enquire_link_loop()

    async def timeout_coro(self, _type, timeout):
        try:
            await asyncio.sleep(timeout)
            print('Failed to receive {0} in {1} seconds'.format(_type, timeout))
            self._close_session()
        except asyncio.CancelledError:
            pass

    def setup_enquire_link_loop(self):
        if self.enquire_link_enabled:
            self.enquire_link_future = asyncio.ensure_future(self.enquire_link_loop(), loop=self.loop)

    async def enquire_link_loop(self):
        try:
            while True:
                try:
                    # Enquire link loop
                    seq_no = self.get_sequence_number()
                    pkt = pdu.enquire_link(seq_no)

                    self.pending_responses[seq_no] = (
                        asyncio.ensure_future(
                            self.timeout_coro('enquire_link_{0}'.format(seq_no),
                                              self.enquire_link_timeout),
                            loop=self.loop
                        ),
                        None
                    )
                    self.transport.write(pkt)
                    print('Sent enquire link')

                    await asyncio.sleep(self.enquire_link_period, loop=self.loop)
                except Exception as err:
                    if isinstance(err, asyncio.CancelledError):
                        raise

                    print('Caught exception {0}'.format(err))
        except asyncio.CancelledError:
            pass

    def _close_session(self):
        self.transport.close()
        self.state = SMPPConnectionState.CLOSED
        try:
            if self.enquire_link_future:
                self.enquire_link_future.cancel()
                self.enquire_link_future = None
        except asyncio.CancelledError:
            pass
        try:
            for value in self.pending_responses.values():
                value.cancel()
        except asyncio.CancelledError:
            pass


# class SMPPManager(object):
#     def __init__(self, loop):
#         self.loop = loop
#
#         self.connections = {}
#
#     async def add_connection(self, name):
#         # lookup name
#
#         conn = await self.loop.create_connection(lambda: SMPPClientProtocol(event_loop), '127.0.0.1', 8888)
#
#         self.connections[name] = conn
#
#
#
# async def main(loop=None):
#     if loop is None:
#         loop = asyncio.get_event_loop()
#
#     manager = SMPPManager(loop=loop)
#     await manager.add_connection('test1')
#
#
#
#
#
#
#
#
# event_loop = asyncio.get_event_loop()
# message = 'Hello World!'
# # coro =
# # event_loop.run_until_complete(coro)
# event_loop.run_until_complete(main(loop=event_loop))
# event_loop.run_forever()
# event_loop.close()
