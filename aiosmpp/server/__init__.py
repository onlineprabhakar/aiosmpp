import argparse
import asyncio
import enum
from typing import Dict, Any

from aiosmpp import pdu


class SMPPSessionState(enum.Enum):
    OPEN = enum.auto()  # Client connected, not yet issued bind #2.2
    BOUND_TX = enum.auto()  # Client connected and bound as TX
    BOUND_RX = enum.auto()  # Client connected and bound as RX
    BOUND_TRX = enum.auto()  # Client connected and bound as TRX
    CLOSED = enum.auto()  # Client as unbound and closed network connection


OPEN_COMMAND_IDS = (pdu.CommandID.BIND_TRANSMITTER, pdu.CommandID.BIND_RECEIVER, pdu.CommandID.BIND_TRANSCEIVER)
ALL_BOUND_COMMAND_IDS = (pdu.CommandID.ENQUIRE_LINK, pdu.CommandID.UNBIND, pdu.CommandID.DATA_SM)
BOUND_TRX_COMMAND_IDS = ALL_BOUND_COMMAND_IDS


class SMPPServer(asyncio.Protocol):
    def __init__(self, *args, **kwargs):
        super(SMPPServer, self).__init__(*args, **kwargs)

        self.transport = None

        self._state = SMPPSessionState.CLOSED
        self.unacknowledged_requests = {}

    @property
    def state(self) -> SMPPSessionState:
        return self._state

    @state.setter
    def state(self, value: SMPPSessionState):
        print('SMPP State transition from {0} -> {1}'.format(self._state, value))
        self._state = value

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from {}'.format(peername))
        self.state = SMPPSessionState.OPEN
        self.transport = transport

    def connection_lost(self, exc):
        self.state = SMPPSessionState.CLOSED

    def data_received(self, data: bytes):
        header = pdu.decode_header(data)
        payload = data[16:]
        command_id = header['id']
        sequence_no = header['seq_no']

        # OPEN, so not bound yet
        if self.state == SMPPSessionState.OPEN:
            if command_id not in OPEN_COMMAND_IDS:
                print('Command ID {0} not supported whilst in OPEN state'.format(command_id))
                self.transport.close()
            elif command_id == pdu.CommandID.BIND_TRANSMITTER:
                self._handle_bind('transmitter', sequence_no, payload)
            elif command_id == pdu.CommandID.BIND_RECEIVER:
                self._handle_bind('receiver', sequence_no, payload)
            else:  # BIND_TRANSCEIVER
                self._handle_bind('tranceiver', sequence_no, payload)

        # ALL BIND TYPES
        elif self.state == SMPPSessionState.BOUND_TRX:
            if command_id not in BOUND_TRX_COMMAND_IDS:
                print('Command ID {0} not supported whilst in BOUND_TRX state'.format(command_id))
                self.transport.close()
            elif command_id == pdu.CommandID.ENQUIRE_LINK:
                print('Sending enquire_link_resp')
                self._handle_enquire_link(sequence_no)
            else:
                # All other stuff, not handled
                raise NotImplementedError()

        else:
            raise NotImplementedError()

    # Handlers
    def _handle_bind(self, _type: str, sequence_id: int, payload: bytes):
        if _type == 'transmitter':
            raise NotImplementedError()
        elif _type == 'receiver':
            raise NotImplementedError()
        else:  # transceiver
            request = pdu.decode_bind_trx(payload)

            if self.handle_bind_transceiver(request):
                # Send resp
                self.state = SMPPSessionState.BOUND_TRX
                response = pdu.bind_trx_resp(sequence_id, 'test smpp')
                self.transport.write(response)
            else:
                # Send nack
                raise NotImplementedError()

    def _handle_enquire_link(self, sequence_id: int):
        # TODO log
        payload = pdu.enquire_link_resp(sequence_id)
        self.transport.write(payload)

    # Handlers to override
    def handle_bind_transmitter(self, request: Dict[str, Any]) -> bool:
        return True

    def handle_bind_receiver(self, request: Dict[str, Any]) -> bool:
        return True

    def handle_bind_transceiver(self, request: Dict[str, Any]) -> bool:
        print('Bind TRX from {0}, pw {1}, system_type {2}'.format(request['system_id'], request['password'], request['system_type']))
        return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', default='0.0.0.0', help='Address to listen on')
    parser.add_argument('--port', default=2775, type=int, help='Port to listen on')

    args = parser.parse_args()

    loop = asyncio.get_event_loop()
    coro = loop.create_server(SMPPServer, args.address, args.port)
    server = loop.run_until_complete(coro)

    # Serve requests until Ctrl+C is pressed
    print('Serving on {0[0]}:{0[1]}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Close the server
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
