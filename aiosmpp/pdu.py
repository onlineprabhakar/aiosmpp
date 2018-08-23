import struct
import enum
from typing import Union, Tuple, Dict, Any, Optional


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


def enquire_link(sequence_number: int) -> bytes:
    return create_header(_id=CommandID.ENQUIRE_LINK,
                         status=Status.ESME_ROK,  # Should be Null in Requsts, ROK == 0x00
                         sequence_number=sequence_number)


def bind_trx_resp(payload):
    index = 0

    system_id, index = read_c_octet_string(payload, index, _max=16)
    tlvs = read_tlvs(payload, index)

    return {
        'system_id': system_id,
        'tlvs': tlvs
    }
