import argparse
import asyncio
import datetime
import enum
import logging
import uuid
from typing import Dict, Any

from aiosmpp import pdu, log, constants as const


class SMPPSessionState(enum.Enum):
    OPEN = enum.auto()  # Client connected, not yet issued bind #2.2
    BOUND_TX = enum.auto()  # Client connected and bound as TX
    BOUND_RX = enum.auto()  # Client connected and bound as RX
    BOUND_TRX = enum.auto()  # Client connected and bound as TRX
    CLOSED = enum.auto()  # Client as unbound and closed network connection


OPEN_COMMAND_IDS = (pdu.CommandID.BIND_TRANSMITTER, pdu.CommandID.BIND_RECEIVER, pdu.CommandID.BIND_TRANSCEIVER)
ALL_BOUND_COMMAND_IDS = (pdu.CommandID.ENQUIRE_LINK, pdu.CommandID.UNBIND, pdu.CommandID.DATA_SM)
BOUND_TRX_COMMAND_IDS = ALL_BOUND_COMMAND_IDS + (pdu.CommandID.SUBMIT_SM, pdu.CommandID.DELIVER_SM_RESP)


class SMPPServer(asyncio.Protocol):
    def __init__(self, *args, logger: logging.Logger, **kwargs):
        super(SMPPServer, self).__init__(*args, **kwargs)

        self.logger = logger
        self.transport = None

        self._state = SMPPSessionState.CLOSED
        self.unacknowledged_requests = {}

        self._sequence_number = 0

    @property
    def sequence_number(self) -> int:
        return self._sequence_number + 1

    @sequence_number.setter
    def sequence_number(self, value: int):
        if value > self._sequence_number:
            self._sequence_number = value

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

        # Store highest sequence number incase we need to asyncronously
        # speak to the client
        self.sequence_number = sequence_no

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
            elif command_id == pdu.CommandID.DELIVER_SM_RESP:
                self._handle_deliver_sm_resp(sequence_no, payload)
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

    def _handle_deliver_sm_resp(self, sequence_id: int, payload: bytes):
        pass

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
        msg_id = str(uuid.uuid4()).lower().replace('-', '')

        self.logger.info('SMS MT {0} -> {1}: {2}'.format(request['source_addr'], request['dest_addr'], request['short_message']))

        coro = self.send_dlr(msg_id, request, const.MessageState.DELIVERED, datetime.datetime.utcnow())
        asyncio.ensure_future(coro)

        # Return MSG ID
        return msg_id

    async def send_dlr(self, msg_id: str, original_request: Dict[str, Any], state: const.MessageState, submit_time: datetime.datetime):
        await asyncio.sleep(10)
        self.logger.info('Sending DELIVRD notification for {0} -> {1}'.format(original_request['source_addr'], original_request['dest_addr']))
        msg = 'id:{0} dlvrd:001 submit date:{1} done date:{2} stat:{3} err:000 text:'.format(
            msg_id,
            submit_time.strftime('%y%M%d%H%M'),
            datetime.datetime.utcnow().strftime('%y%M%d%H%M'),
            state.short
        ).encode()

        payload = pdu.deliver_sm(
            self.sequence_number,
            service_type='',
            source_addr_ton=original_request['source_addr_ton'],
            source_addr_npi=original_request['source_addr_npi'],
            source_addr=original_request['source_addr'],
            dest_addr_ton=original_request['dest_addr_ton'],
            dest_addr_npi=original_request['dest_addr_npi'],
            dest_addr=original_request['dest_addr'],
            esm_class=int(const.ESMClass.MESSAGE_TYPE_CONTAINS_ACK),
            protocol_id=0x00,
            priority_flag=int(const.PriorityFlag.LEVEL_0),
            schedule_delivery_time=original_request['schedule_delivery_time'],
            validity_period=original_request['validity_period'],
            registered_delivery=original_request['registered_delivery'],
            replace_if_present_flag=original_request['replace_if_present_flag'],
            data_coding=original_request['replace_if_present_flag'],
            sm_default_msg_id=0x00,
            sm_length=len(msg),
            short_message=msg
        )
        # TODO setup timer to catch the resp
        self.transport.write(payload)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--address', default='0.0.0.0', help='Address to listen on')
    parser.add_argument('--port', default=2775, type=int, help='Port to listen on')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose mode')

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logger = log.get_stdout_logger('server', log_level)

    loop = asyncio.get_event_loop()
    server_coro = loop.create_server(lambda: SMPPServer(logger=logger), args.address, args.port)
    server = loop.run_until_complete(server_coro)

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
