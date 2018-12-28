import asyncio
import binascii
import enum
import logging
from typing import Optional, Dict, Any, Callable, Union

from aiosmpp import pdu


class SMPPConnectionState(enum.Enum):
    OPEN = enum.auto()
    BOUND_TX = enum.auto()
    BOUND_RX = enum.auto()
    BOUND_TRX = enum.auto()
    CLOSED = enum.auto()


class SMPPClientProtocol(asyncio.Protocol):
    def __init__(self, config, loop: Optional[asyncio.AbstractEventLoop] = None,
                 logger: Optional[logging.Logger] = None):
        self.loop = loop
        self.smpp_min_verison = 0x34
        if not loop:
            self.loop = asyncio.get_event_loop()

        self.logger = logger
        if not logger:
            self.logger = logging.getLogger()

        self.transport = None
        self.config: Dict[str, Any] = config
        self.state: SMPPConnectionState = SMPPConnectionState.CLOSED

        self.conn_lost_trigger: Callable[[], None] = lambda: None
        self.deliver_sm_trigger: Callable[[Dict[str, Any]], None] = lambda: None

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
        self.submit_sm_resp_timeout = 0.15  # 150ms

    def __del__(self):
        self.close()

    def close(self):
        try:
            self._close_session()
        except:  # noqa: E722
            pass

    def set_connection_lost_callback(self, func: Callable[[], None]):
        self.conn_lost_trigger = func

    def set_deliver_sm_callback(self, func: Callable[[], None]):
        self.deliver_sm_trigger = func

    def get_sequence_number(self) -> int:
        result = self._seq_number
        self._seq_number += 1

        return result

    def connection_made(self, transport: asyncio.Transport):
        self.transport = transport
        self.logger.debug('Connected to {0[0]}:{0[1]}'.format(self.transport.get_extra_info('peername')))
        self.state = SMPPConnectionState.OPEN

    def data_received(self, data: bytes):
        self.logger.debug('Data received: {0}'.format(binascii.hexlify(data).decode()))

        if len(data) < 16:
            print('Recieved pkt len less than 16 bytes, invalid header')
            return

        hdr = pdu.decode_header(data)

        if hdr['seq_no'] in self.pending_responses:
            timeout_future, handler, future = self.pending_responses.pop(hdr['seq_no'])
            timeout_future.cancel()
            if handler:
                result = handler(hdr)
                if future:
                    future.set_result(result)

            if future:  # Work if no handler is supplied
                future.done()
            return

        if hdr['id'] == pdu.CommandID.DELIVER_SM:
            self.deliver_sm(hdr)

            return

        # All else fails
        self.logger.critical('No req matching {0}'.format(hdr['seq_no']))

    def connection_lost(self, exc):
        self.logger.warning('Lost connection to {0[0]}:{0[1]}'.format(self.transport.get_extra_info('peername')))
        self.state = SMPPConnectionState.CLOSED

        self._close_session()

        # Trigger callback for connection lost
        self.conn_lost_trigger()

    def bind_trx(self, asyncio_future: Optional[asyncio.Future] = None):
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
            asyncio.ensure_future(self.timeout_coro('bind_trx', self.bind_resp_timeout, asyncio_future),
                                  loop=self.loop),
            self.bind_trx_resp,
            asyncio_future
        )
        self.transport.write(pkt)
        self.logger.debug('Requested TRX bind')

        return seq_no

    def bind_trx_resp(self, pkt: Dict[str, Any]):
        self.logger.debug('Got Bind TRX response {0}'.format(pkt))

        if pkt['status'] != pdu.Status.ESME_ROK:
            self.logger.critical('TRX Bind did not get ESME_ROK')
            self._close_session()
            return

        bind_resp = pdu.decode_bind_trx_resp(pkt['payload'])

        if 0x0210 in bind_resp['tlvs'] and bind_resp['tlvs'][0x0210] > self.smpp_min_verison:
            self.logger.critical('SMPP Server minimum version ({0}) is '
                                 'higher than ours, cant continue'.format(bind_resp['tlvs'][0x0210]))
            self._close_session()
            return

        self.state = SMPPConnectionState.BOUND_TRX
        self.logger.info('TRX Bound')

        self.setup_enquire_link_loop()

        return bind_resp

    async def timeout_coro(self, _type, timeout, future: Optional[asyncio.Future] = None):
        try:
            await asyncio.sleep(timeout)
            if future:
                future.set_exception(TimeoutError('Failed to receive {0} in {1} seconds'.format(_type, timeout)))
            self.logger.warning('Failed to receive {0} in {1} seconds'.format(_type, timeout))
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
                        asyncio.ensure_future(self.timeout_coro('enquire_link_{0}'.format(seq_no),
                                                                self.enquire_link_timeout), loop=self.loop),
                        None,  # Callback to process packet
                        None  # Event to trigger
                    )
                    self.transport.write(pkt)
                    self.logger.debug('Sent enquire link')

                    await asyncio.sleep(self.enquire_link_period, loop=self.loop)
                except Exception as err:
                    if isinstance(err, asyncio.CancelledError):
                        raise

                    self.logger.exception('Caught exception in enquire link loop', exc_info=err)
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
            for values in self.pending_responses.values():
                # element 0 is the task
                values[0].cancel()
        except asyncio.CancelledError:
            pass

    async def send_submit_sm(self, timeout: float = 0.5, **kwargs):
        """
        :throws asyncio.TimeoutError: When
        """

        future = asyncio.Future()

        self.submit_sm(**kwargs, asyncio_future=future)

        try:
            await asyncio.wait_for(future, timeout=timeout)
            return future.result()
        except asyncio.TimeoutError as err:
            self.logger.error('submit_sm timed out: {0}'.format(err))
            raise
        except Exception as err:
            self.logger.exception('Caught exception whilst submitsm', exc_info=err)

        return None

    def deliver_sm(self, pkt: Dict[str, Any]):
        self.logger.debug('Got DELIVER_SM {0}'.format(pkt))

        if pkt['status'] != pdu.Status.ESME_ROK:
            self.logger.critical('DELIVER_SM did not get ESME_ROK status, got: {0}'.format(pkt['status']))

        pkt['payload'] = pdu.decode_deliver_sm(pkt['payload'])

        seq_no = self.get_sequence_number()
        response_pkt = pdu.deliver_sm_resp(seq_no)
        self.transport.write(response_pkt)
        self.logger.debug('Sent DELIVER_SM_RESP')

        if self.deliver_sm_trigger:
            try:
                self.deliver_sm_trigger(pkt)
            except:  # noqa: E722
                pass

    def submit_sm(self,
                  service_type: str,
                  source_addr_ton: int,
                  source_addr_npi: int,
                  source_addr: str,
                  dest_addr_ton: int,
                  dest_addr_npi: int,
                  destination_addr: str,
                  esm_class: int,
                  protocol_id: int,
                  priority_flag: int,
                  schedule_delivery_time: str,
                  validity_period: str,
                  registered_delivery: int,
                  replace_if_present_flag: int,
                  data_coding: int,
                  sm_default_msg_id,
                  short_message: Union[bytes, str],
                  asyncio_future: Optional[asyncio.Future] = None):
        seq_no = self.get_sequence_number()

        sm_length = len(short_message)
        if not isinstance(short_message, bytes):
            short_message = short_message.encode()

        pkt = pdu.submit_sm(
            sequence_number=seq_no,
            service_type=service_type,
            source_addr_ton=source_addr_ton,
            source_addr_npi=source_addr_npi,
            source_addr=source_addr,
            dest_addr_ton=dest_addr_ton,
            dest_addr_npi=dest_addr_npi,
            destination_addr=destination_addr,
            esm_class=esm_class,
            protocol_id=protocol_id,
            priority_flag=priority_flag,
            schedule_delivery_time=schedule_delivery_time,
            validity_period=validity_period,
            registered_delivery=registered_delivery,
            replace_if_present_flag=replace_if_present_flag,
            data_coding=data_coding,
            sm_default_msg_id=sm_default_msg_id,
            sm_length=sm_length,
            short_message=short_message
        )

        self.pending_responses[seq_no] = (
            asyncio.ensure_future(
                self.timeout_coro('submit_sm', self.submit_sm_resp_timeout, asyncio_future),
                loop=self.loop
            ),
            self.submit_sm_resp,
            asyncio_future
        )
        self.transport.write(pkt)
        self.logger.debug('Sent submit_sm')

        return seq_no

    def submit_sm_resp(self, pkt: Dict[str, Any]):
        self.logger.debug('Got submit_sm_resp response {0}'.format(pkt))

        if pkt['status'] != pdu.Status.ESME_ROK:
            self.logger.critical('submit_sm did not get ESME_ROK')

        try:
            pkt['payload'] = pdu.decode_submit_sm_resp(pkt['payload'])
        except Exception as err:
            self.logger.exception('Failed to decode submit_sm_resp, payload: {0}'.format(
                binascii.hexlify(pkt['payload'])), exc_info=err
            )

        return pkt
