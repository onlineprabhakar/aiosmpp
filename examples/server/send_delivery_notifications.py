import asyncio
import datetime
from typing import Dict, Any

from aiosmpp.server import RawSMPPServer, run_server, get_args
from aiosmpp import constants as const
from aiosmpp import pdu


class DLRSMPPServer(RawSMPPServer):
    def handle_submit_sm(self, request: Dict[str, Any]) -> str:
        # Get msg id, from calling the method of the superclass (also does logging)
        msg_id = super(DLRSMPPServer, self).handle_submit_sm(request)

        submit_time = datetime.datetime.utcnow()

        # Needs delivery
        registered_delivery = const.RegisteredDeliveryReceipt(request['registered_delivery'])
        if registered_delivery in (const.RegisteredDeliveryReceipt.SMSC_DELIVERY_RECEIPT_REQUESTED, const.RegisteredDeliveryReceipt.SMSC_DELIVERY_RECEIPT_REQUESTED_FOR_FAILURE):
            coro = self.send_dlr(msg_id, request, const.MessageState.DELIVERED, submit_time, delay_time=5)
            asyncio.ensure_future(coro)

        # Return MSG ID, this'll go in the submit sm
        return msg_id

    async def send_dlr(self, msg_id: str, original_request: Dict[str, Any], state: const.MessageState, submit_time: datetime.datetime, delay_time: int=10):
        # Cheap hack to delay DLR for an arbitrary time
        await asyncio.sleep(delay_time)

        # SMPP Message states ENUM has a short property which converts the longer formats into those which goes in a DLR
        self.logger.info('Sending {0} notification for {1} -> {2}'.format(state.short, original_request['source_addr'], original_request['dest_addr']))
        # Format of the message is in SMPP Spec v3.4 Appendix B DLR Format, page ~167
        msg = 'id:{0} sub:001 dlvrd:001 submit date:{1} done date:{2} stat:{3} err:000 text:'.format(
            msg_id,
            submit_time.strftime('%y%M%d%H%M'),
            datetime.datetime.utcnow().strftime('%y%M%d%H%M'),
            state.short
        ).encode()

        # Create delivery notification, copy most of the values from the submit_sm request
        payload = pdu.deliver_sm(
            self.sequence_number,
            service_type='',
            source_addr_ton=original_request['source_addr_ton'],
            source_addr_npi=original_request['source_addr_npi'],
            source_addr=original_request['source_addr'],
            dest_addr_ton=original_request['dest_addr_ton'],
            dest_addr_npi=original_request['dest_addr_npi'],
            dest_addr=original_request['dest_addr'],
            esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_CONTAINS_DELIVERY_ACK),
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
        # TODO setup timer to ensure ESME replies with deliver_sm_resp
        self.transport.write(payload)

        coro = self.send_mo()
        # noinspection PyAsyncCall
        asyncio.ensure_future(coro)

    async def send_mo(self):
        # Cheap hack to delay DLR for an arbitrary time
        await asyncio.sleep(5)

        # SMPP Message states ENUM has a short property which converts the longer formats into those which goes in a DLR
        self.logger.info('Sending MO notification')

        msg = 'Hello'.encode()

        # Create delivery notification, copy most of the values from the submit_sm request
        payload = pdu.deliver_sm(
            self.sequence_number,
            service_type='',
            source_addr_ton=const.AddrTON.INTERNATIONAL,
            source_addr_npi=const.AddrNPI.ISDN,
            source_addr='447111111111',
            dest_addr_ton=const.AddrTON.INTERNATIONAL,
            dest_addr_npi=const.AddrNPI.ISDN,
            dest_addr='447222222222',
            esm_class=int(const.ESMClassInbound.MESSAGE_TYPE_DEFAULT),
            protocol_id=0x00,
            priority_flag=int(const.PriorityFlag.LEVEL_0),
            schedule_delivery_time=None,  # Always Null
            validity_period=None,  # Always Null
            registered_delivery=const.RegisteredDeliveryReceipt.NO_SMSC_DELIVERY_RECEIPT_REQUESTED,
            replace_if_present_flag=0x00,  # Always Null
            data_coding=0x00,
            sm_default_msg_id=0x00,  # Always Null
            sm_length=len(msg),
            short_message=msg
        )
        # TODO setup timer to ensure ESME replies with deliver_sm_resp
        self.transport.write(payload)


if __name__ == '__main__':
    run_server(smpp_class=DLRSMPPServer, **get_args())
