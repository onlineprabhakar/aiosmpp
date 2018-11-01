import struct
import enum
from typing import Union, Tuple, List, Dict, Any, Optional


class DecodeException(Exception):
    pass


class CommandID(enum.IntEnum):
    GENERIC_NACK = 0x80000000
    BIND_RECEIVER = 0x00000001
    BIND_RECEIVER_RESP = 0x80000001
    BIND_TRANSMITTER = 0x00000002
    BIND_TRANSMITTER_RESP = 0x80000002
    QUERY_SM = 0x00000003
    QUERY_SM_RESP = 0x80000003
    SUBMIT_SM = 0x00000004
    SUBMIT_SM_RESP = 0x80000004
    DELIVER_SM = 0x00000005
    DELIVER_SM_RESP = 0x80000005
    UNBIND = 0x00000006
    UNBIND_RESP = 0x80000006
    REPLACE_SM = 0x00000007
    REPLACE_SM_RESP = 0x80000007
    CANCEL_SM = 0x00000008
    CANCEL_SM_RESP = 0x80000008
    BIND_TRANSCEIVER = 0x00000009
    BIND_TRANSCEIVER_RESP = 0x80000009
    ENQUIRE_LINK = 0x00000015
    ENQUIRE_LINK_RESP = 0x80000015
    SUBMIT_MULTI = 0x00000021
    SUBMIT_MULTI_RESP = 0x80000021
    ALERT_NOTIFICATION = 0x00000102
    DATA_SM = 0x00000103
    DATA_SM_RESP = 0x80000103


class Status(enum.IntEnum):
    ESME_ROK = 0x00000000
    ESME_RINVMSGLEN = 0x00000001
    ESME_RINVCMDLEN = 0x00000002
    ESME_RINVCMDID = 0x00000003
    ESME_RINVBNDSTS = 0x00000004
    ESME_RALYBND = 0x00000005
    ESME_RINVPRTFLG = 0x00000006
    ESME_RINVREGDLVFLG = 0x00000007
    ESME_RSYSERR = 0x00000008
    ESME_RINVSRCADR = 0x0000000A
    ESME_RINVDSTADR = 0x0000000B
    ESME_RINVMSGID = 0x0000000C
    ESME_RBINDFAIL = 0x0000000D
    ESME_RINVPASWD = 0x0000000E
    ESME_RINVSYSID = 0x0000000F
    ESME_RCANCELFAIL = 0x00000011
    ESME_RREPLACEFAIL = 0x00000013
    ESME_RMSGQFUL = 0x00000014
    ESME_RINVSERTYP = 0x00000015
    ESME_RINVNUMDESTS = 0x00000033
    ESME_RINVDLNAME = 0x00000034
    ESME_RINVDESTFLAG = 0x00000040
    ESME_RINVSUBREP = 0x00000042
    ESME_RINVESMCLASS = 0x00000043
    ESME_RCNTSUBDL = 0x00000044
    ESME_RSUBMITFAIL = 0x00000045
    ESME_RINVSRCTON = 0x00000048
    ESME_RINVSRCNPI = 0x00000049
    ESME_RINVDSTTON = 0x00000050
    ESME_RINVDSTNPI = 0x00000051
    ESME_RINVSYSTYP = 0x00000053
    ESME_RINVREPFLAG = 0x00000054
    ESME_RINVNUMMSGS = 0x00000055
    ESME_RTHROTTLED = 0x00000058
    ESME_RINVSCHED = 0x00000061
    ESME_RINVEXPIRY = 0x00000062
    ESME_RINVDFTMSGID = 0x00000063
    ESME_RX_T_APPN = 0x00000064
    ESME_RX_P_APPN = 0x00000065
    ESME_RX_R_APPN = 0x00000066
    ESME_RQUERYFAIL = 0x00000067
    ESME_RINVOPTPARSTREAM = 0x000000C0
    ESME_ROPTPARNOTALLWD = 0x000000C1
    ESME_RINVPARLEN = 0x000000C2
    ESME_RMISSINGOPTPARAM = 0x000000C3
    ESME_RINVOPTPARAMVAL = 0x000000C4
    ESME_RDELIVERYFAILURE = 0x000000FE
    ESME_RUNKNOWNERR = 0x000000FF


TLV_MAP = {
    0x0210: ('sc_interface_version', lambda value: ord(value))  # 5.3.2.25 - e.g. 0x34 -> 3.4
}


def octet_string(value: Optional[bytes], _max: int=0) -> bytes:
    if value is None:
        return b'\x00'

    if 0 < _max < len(value):
        value = value[:_max]

    return value


def read_octet_string(value: bytes, index: int=0, _max: int=0) -> Tuple[Union[bytes, None], int]:
    start = index

    payload_len = len(value)
    _max += index
    while index < _max and index < payload_len:
        index += 1

    if value[start:index] == b'\x00':
        return None, index

    # index-1 then decodes string excluding the null byte
    return value[start:index], index


def c_octet_string(value: Optional[str], _max: int=0) -> bytes:
    if value is None:
        return b'\x00'

    if _max > 0 and len(value) > _max -1:
        value = value[:_max-1]

    return value.encode() + b'\x00'


def read_c_octet_string(value: bytes, index: int=0, _max: int=0) -> Tuple[Union[str, None], int]:
    start = index

    _max += index
    while index < _max:
        if value[index] == 0x00:
            index += 1
            break
        index += 1
    else:
        raise DecodeException('Incorrect coctet-string')

    if value[start:index] == b'\x00':
        return None, index

    # index-1 then decodes string excluding the null byte
    return value[start:index-1].decode(), index


def read_integer(value: bytes, index: int, octets: int) -> Tuple[int, int]:
    result = 0

    if octets == 1:
        result = value[index]
    if octets == 2:
        result = struct.unpack_from('>H', value, index)
    if octets == 4:
        result = struct.unpack_from('>I', value, index)
    if octets == 8:
        result = struct.unpack_from('>Q', value, index)

    return result, index + octets


def read_tlv(payload: bytes, index: int=0) -> Tuple[int, bytes, int]:
    tag, length = struct.unpack_from('>HH', payload, index)
    index += 4
    data = payload[index:index+length]

    return tag, data, index + length


def read_tlvs(payload: bytes, index: int=0) -> Dict[int, Any]:
    result = {}

    payload_len = len(payload)
    while index < payload_len:
        tag, data, index = read_tlv(payload, index)
        if tag in TLV_MAP:
            # tag -> (name, formatter_func)
            data = TLV_MAP[tag][1](data)
        result[tag] = data

    return result


def create_tlv(tag: int, payload: bytes, length: int=None) -> bytes:
    if length is None:
        length = len(payload)

    return struct.pack('>HH', tag, length) + payload


def integer(value: Optional[int], octets: int=1) -> bytes:
    if value is None:
        return b'\x00'

    if octets == 1:
        return bytes([value])
    if octets == 2:
        return struct.pack('>H', value)
    if octets == 4:
        return struct.pack('>I', value)
    if octets == 8:
        return struct.pack('>Q', value)

    raise AttributeError('octets not one of 1,2,4,8')


def create_header(_id: int, status: int, sequence_number: int, payload: Optional[bytes]=None) -> bytes:
    if payload is None:
        payload = b''
    packet_length = len(payload) + 16  # 4+4+4+4 for header size

    return struct.pack('>IIII', packet_length, _id, status, sequence_number) + payload


def decode_header(payload: bytes) -> Dict[str, Any]:
    values = struct.unpack_from('>IIII', payload, 0)

    return {
        'length': values[0],
        'id': values[1],
        'status': values[2],
        'seq_no': values[3],
        'payload': payload[16:]
    }


# Enquire link
def enquire_link(sequence_number: int) -> bytes:
    return create_header(_id=CommandID.ENQUIRE_LINK,
                         status=Status.ESME_ROK,  # Should be Null in Requsts, ROK == 0x00
                         sequence_number=sequence_number)


def enquire_link_resp(sequence_number: int) -> bytes:
    return create_header(_id=CommandID.ENQUIRE_LINK_RESP,
                         status=Status.ESME_ROK,
                         sequence_number=sequence_number)


# Bind TRX
def bind_trx(sequence_number: int,
             system_id: str,
             password: str,
             system_type: Optional[str]=None,
             interface_version: int=0x34,
             addr_ton: Optional[int]=None,
             addr_npi: Optional[int]=None,
             address_range: Optional[str]=None) -> bytes:

    buffer = c_octet_string(system_id, _max=16)
    buffer += c_octet_string(password, _max=9)
    buffer += c_octet_string(system_type, _max=16)
    buffer += integer(interface_version, octets=1)
    buffer += integer(addr_ton, octets=1)
    buffer += integer(addr_npi, octets=1)
    buffer += c_octet_string(address_range, _max=41)

    return create_header(_id=CommandID.BIND_TRANSCEIVER,
                         status=Status.ESME_ROK,  # Should be Null in Requsts, ROK == 0x00
                         sequence_number=sequence_number,
                         payload=buffer)


def decode_bind_trx(payload: bytes, index: int=0) -> Dict[str, Any]:
    system_id, index = read_c_octet_string(payload, index, _max=16)
    password, index = read_c_octet_string(payload, index, _max=9)
    system_type, index = read_c_octet_string(payload, index, _max=16)
    interface_version, index = read_integer(payload, index, octets=1)
    addr_ton, index = read_integer(payload, index, octets=1)
    addr_npi, index = read_integer(payload, index, octets=1)
    address_range, index = read_c_octet_string(payload, index, _max=41)

    return {
        'system_id': system_id,
        'password': password,
        'system_type': system_type,
        'interface_version': interface_version,
        'addr_ton': addr_ton,
        'addr_npi': addr_npi,
        'address_range': address_range
    }


def bind_trx_resp(sequence_number: int,
                  system_id: str,
                  interface_version: int=0x34) -> bytes:

    buffer = c_octet_string(system_id, _max=16)
    buffer += create_tlv(tag=0x0210, payload=bytes([interface_version]))

    return create_header(_id=CommandID.BIND_TRANSCEIVER_RESP,
                         status=Status.ESME_ROK,
                         sequence_number=sequence_number,
                         payload=buffer)


def decode_bind_trx_resp(payload: bytes, index: int=0) -> Dict[str, Any]:
    system_id, index = read_c_octet_string(payload, index, _max=16)
    tlvs = read_tlvs(payload, index)

    return {
        'system_id': system_id,
        'tlvs': tlvs
    }


# Submit SM
def submit_sm(sequence_number: int, service_type: str, source_addr_ton: int, source_addr_npi: int, source_addr: str,
              dest_addr_ton: int, dest_addr_npi: int, destination_addr: str, esm_class: int, protocol_id: int, priority_flag: int,
              schedule_delivery_time: str, validity_period: str, registered_delivery: int, replace_if_present_flag: int, data_coding: int,
              sm_default_msg_id, sm_length, short_message) -> bytes:

    buffer = c_octet_string(service_type, _max=6)
    buffer += integer(source_addr_ton, octets=1)
    buffer += integer(source_addr_npi, octets=1)
    buffer += c_octet_string(source_addr, _max=21)
    buffer += integer(dest_addr_ton, octets=1)
    buffer += integer(dest_addr_npi, octets=1)
    buffer += c_octet_string(destination_addr, _max=21)
    buffer += integer(esm_class, octets=1)
    buffer += integer(protocol_id, octets=1)
    buffer += integer(priority_flag, octets=1)
    buffer += c_octet_string(schedule_delivery_time, _max=17)
    buffer += c_octet_string(validity_period, _max=17)
    buffer += integer(registered_delivery, octets=1)
    buffer += integer(replace_if_present_flag, octets=1)
    buffer += integer(data_coding, octets=1)
    buffer += integer(sm_default_msg_id, octets=1)
    buffer += integer(sm_length, octets=1)
    buffer += octet_string(short_message, _max=254)

    return create_header(_id=CommandID.SUBMIT_SM,
                         status=Status.ESME_ROK,  # Should be Null in Requsts, ROK == 0x00
                         sequence_number=sequence_number,
                         payload=buffer)


def decode_submit_sm(payload: bytes, index: int=0) -> Dict[str, Any]:
    service_type, index = read_c_octet_string(payload, index, _max=6)
    source_addr_ton, index = read_integer(payload, index, octets=1)
    source_addr_npi, index = read_integer(payload, index, octets=1)
    source_addr, index = read_c_octet_string(payload, index, _max=21)
    dest_addr_ton, index = read_integer(payload, index, octets=1)
    dest_addr_npi, index = read_integer(payload, index, octets=1)
    dest_addr, index = read_c_octet_string(payload, index, _max=21)
    esm_class, index = read_integer(payload, index, octets=1)
    protocol_id, index = read_integer(payload, index, octets=1)
    priority_flag, index = read_integer(payload, index, octets=1)
    schedule_delivery_time, index = read_c_octet_string(payload, index, _max=17)
    validity_period, index = read_c_octet_string(payload, index, _max=17)
    registered_delivery, index = read_integer(payload, index, octets=1)
    replace_if_present_flag, index = read_integer(payload, index, octets=1)
    data_coding, index = read_integer(payload, index, octets=1)
    sm_default_msg_id, index = read_integer(payload, index, octets=1)
    sm_length, index = read_integer(payload, index, octets=1)
    short_message, index = read_octet_string(payload, index, _max=254)

    tlvs = read_tlvs(payload, index)

    return {
        'service_type': service_type,
        'source_addr_ton': source_addr_ton,
        'source_addr_npi': source_addr_npi,
        'source_addr': source_addr,
        'dest_addr_ton': dest_addr_ton,
        'dest_addr_npi': dest_addr_npi,
        'dest_addr': dest_addr,
        'esm_class': esm_class,
        'protocol_id': protocol_id,
        'priority_flag': priority_flag,
        'schedule_delivery_time': schedule_delivery_time,
        'validity_period': validity_period,
        'registered_delivery': registered_delivery,
        'replace_if_present_flag': replace_if_present_flag,
        'data_coding': data_coding,
        'sm_default_msg_id': sm_default_msg_id,
        'sm_length': sm_length,
        'short_message': short_message,
        'tlvs': tlvs
    }


def submit_sm_resp(sequence_number: int, msg_id: str, status=Status.ESME_ROK) -> bytes:
    buffer = b''

    if status == Status.ESME_ROK:
        buffer += c_octet_string(msg_id, _max=65)

    return create_header(_id=CommandID.SUBMIT_SM_RESP,
                         status=status,
                         sequence_number=sequence_number,
                         payload=buffer)


def decode_submit_sm_resp(payload: bytes, index: int=0) -> Dict[str, Any]:
    message_id, index = read_c_octet_string(payload, index, _max=65)
    tlvs = read_tlvs(payload, index)

    return {
        'message_id': message_id,
        'tlvs': tlvs
    }


# Deliver SM
def deliver_sm(sequence_number: int,
               service_type: str,
               source_addr_ton: int,
               source_addr_npi: int,
               source_addr: str,
               dest_addr_ton: int,
               dest_addr_npi: int,
               dest_addr: str,
               esm_class: int,
               protocol_id: int,
               priority_flag: int,
               schedule_delivery_time: str,
               validity_period: str,
               registered_delivery: int,
               replace_if_present_flag: int,
               data_coding: int,
               sm_default_msg_id: int,
               sm_length: int,
               short_message: bytes,
               tlvs: Optional[List[bytes]]=None) -> bytes:

    buffer = c_octet_string(service_type, _max=6)
    buffer += integer(source_addr_ton, octets=1)
    buffer += integer(source_addr_npi, octets=1)
    buffer += c_octet_string(source_addr, _max=21)
    buffer += integer(dest_addr_ton, octets=1)
    buffer += integer(dest_addr_npi, octets=1)
    buffer += c_octet_string(dest_addr, _max=21)
    buffer += integer(esm_class, octets=1)
    buffer += integer(protocol_id, octets=1)
    buffer += integer(priority_flag, octets=1)
    buffer += c_octet_string(schedule_delivery_time, _max=1)
    buffer += c_octet_string(validity_period, _max=1)
    buffer += integer(registered_delivery, octets=1)
    buffer += integer(replace_if_present_flag, octets=1)
    buffer += integer(data_coding, octets=1)
    buffer += integer(sm_default_msg_id, octets=1)
    buffer += integer(sm_length, octets=1)
    buffer += octet_string(short_message, _max=254)

    if tlvs:
        for tlv in tlvs:
            buffer += tlv

    return create_header(_id=CommandID.DELIVER_SM,
                         status=Status.ESME_ROK,
                         sequence_number=sequence_number,
                         payload=buffer)


def decode_deliver_sm_resp(payload: bytes, index: int=0) -> Dict[str, Any]:
    service_type, index = read_c_octet_string(payload, index, _max=6)
    source_addr_ton, index = read_integer(payload, index, octets=1)
    source_addr_npi, index = read_integer(payload, index, octets=1)
    source_addr, index = read_c_octet_string(payload, index, _max=21)
    dest_addr_ton, index = read_integer(payload, index, octets=1)
    dest_addr_npi, index = read_integer(payload, index, octets=1)
    dest_addr, index = read_c_octet_string(payload, index, _max=21)
    esm_class, index = read_integer(payload, index, octets=1)
    protocol_id, index = read_integer(payload, index, octets=1)
    priority_flag, index = read_integer(payload, index, octets=1)
    schedule_delivery_time, index = read_c_octet_string(payload, index, _max=1)
    validity_period, index = read_c_octet_string(payload, index, _max=1)
    registered_delivery, index = read_integer(payload, index, octets=1)
    replace_if_present_flag, index = read_integer(payload, index, octets=1)
    data_coding, index = read_integer(payload, index, octets=1)
    sm_default_msg_id, index = read_integer(payload, index, octets=1)
    sm_length, index = read_integer(payload, index, octets=1)
    short_message, index = read_octet_string(payload, index, _max=254)
    tlvs = read_tlvs(payload, index)

    return {
        'service_type': service_type,
        'source_addr_ton': source_addr_ton,
        'source_addr_npi': source_addr_npi,
        'source_addr': source_addr,
        'dest_addr_ton': dest_addr_ton,
        'dest_addr_npi': dest_addr_npi,
        'dest_addr': dest_addr,
        'esm_class': esm_class,
        'protocol_id': protocol_id,
        'priority_flag': priority_flag,
        'schedule_delivery_time': schedule_delivery_time,
        'validity_period': validity_period,
        'registered_delivery': registered_delivery,
        'replace_if_present_flag': replace_if_present_flag,
        'data_coding': data_coding,
        'sm_default_msg_id': sm_default_msg_id,
        'sm_length': sm_length,
        'short_message': short_message,
        'tlvs': tlvs
    }


def deliver_sm_resp(sequence_number: int) -> bytes:

    buffer = c_octet_string(None, _max=1)

    return create_header(_id=CommandID.DELIVER_SM_RESP,
                         status=Status.ESME_ROK,
                         sequence_number=sequence_number,
                         payload=buffer)
