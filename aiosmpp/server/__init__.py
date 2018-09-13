import argparse
import asyncio
import enum
import logging
import uuid
from typing import Dict, Any

from aiosmpp import pdu, log


class SMPPSessionState(enum.Enum):
    OPEN = enum.auto()  # Client connected, not yet issued bind #2.2
    BOUND_TX = enum.auto()  # Client connected and bound as TX
    BOUND_RX = enum.auto()  # Client connected and bound as RX
    BOUND_TRX = enum.auto()  # Client connected and bound as TRX
    CLOSED = enum.auto()  # Client as unbound and closed network connection


OPEN_COMMAND_IDS = (pdu.CommandID.BIND_TRANSMITTER, pdu.CommandID.BIND_RECEIVER, pdu.CommandID.BIND_TRANSCEIVER)
ALL_BOUND_COMMAND_IDS = (pdu.CommandID.ENQUIRE_LINK, pdu.CommandID.UNBIND, pdu.CommandID.DATA_SM)
BOUND_TRX_COMMAND_IDS = ALL_BOUND_COMMAND_IDS + (pdu.CommandID.SUBMIT_SM,)


class SMPPServer(asyncio.Protocol):
    def __init__(self, *args, logger: logging.Logger, **kwargs):
        super(SMPPServer, self).__init__(*args, **kwargs)

        self.logger = logger
        self.transport = None

        self._state = SMPPSessionState.CLOSED
        self.unacknowledged_requests = {}

    @property
    def state(self) -> SMPPSessionState:
        return self._state

    @state.setter
    def state(self, value: SMPPSessionState):
        self.logger.debug('SMPP State transition from {0} -> {1}'.format(self._state, value))
        self._state = value

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        self.logger.info('Connection from {}'.format(peername))
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
                self.logger.warning('Command ID {0} not supported whilst in OPEN state. Closing'.format(command_id))
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
                self.logger.warning('Command ID {0} not supported whilst in BOUND_TRX state. Closing'.format(command_id))
                self.transport.close()
            elif command_id == pdu.CommandID.ENQUIRE_LINK:
                self.logger.debug('Sending enquire_link_resp')
                self._handle_enquire_link(sequence_no)
            elif command_id == pdu.CommandID.SUBMIT_SM:
                self._handle_submit_sm(sequence_no, payload)
            else:
                # All other stuff, not handled
                self.logger.error('Unknown command id {0}'.format(command_id))
                raise NotImplementedError()

        else:
            self.logger.error('Unknown state'.format(self.state))
            raise NotImplementedError()

    # Handlers
    def _handle_bind(self, _type: str, sequence_id: int, payload: bytes):
        if _type == 'transmitter':
            self.logger.error('transmitter bind not implemented')
            raise NotImplementedError()
        elif _type == 'receiver':
            self.logger.error('receiver bind not implemented')
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

    def _handle_submit_sm(self, sequence_id: int, payload: bytes):
        request = pdu.decode_submit_sm(payload)

        # TODO raise SMPPError with errocode + msg to log out
        msg_id = self.handle_submit_sm(request)

        response = pdu.submit_sm_resp(sequence_id, msg_id, status=pdu.Status.ESME_ROK)
        self.transport.write(response)
        

    # Handlers to override
    def handle_bind_transmitter(self, request: Dict[str, Any]) -> bool:
        return True

    def handle_bind_receiver(self, request: Dict[str, Any]) -> bool:
        return True

    def handle_bind_transceiver(self, request: Dict[str, Any]) -> bool:
        self.logger.info('Bind TRX from {0}, pw {1}, system_type {2}'.format(request['system_id'], request['password'], request['system_type']))
        return True

    def handle_submit_sm(self, request: Dict[str, Any]) -> str:
        # TODO deal with all the logic of msg combining, getting short_message from tlv if needed
        #
        self.logger.info('SMS MT {0} -> {1}: {2}'.format(request['source_addr'], request['dest_addr'], request['short_message']))

        # TODO schedule DLRs

        # Return MSG ID
        msg_id = str(uuid.uuid4()).upper().replace('-', '')
        return msg_id


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', default='0.0.0.0', help='Address to listen on')
    parser.add_argument('--port', default=2775, type=int, help='Port to listen on')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode')

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = log.get_stdout_logger('server', log_level)

    loop = asyncio.get_event_loop()
    coro = loop.create_server(lambda: SMPPServer(logger=logger), args.address, args.port)
    server = loop.run_until_complete(coro)

    # Serve requests until Ctrl+C is pressed
    logger.info('Serving on {0[0]}:{0[1]}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    # Close the server
    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
