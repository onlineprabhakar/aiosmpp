import pytest

from aiosmpp import pdu


def test_create_octet_string_none():
    result = pdu.octet_string(value=None)

    assert result == b'\x00'


@pytest.mark.parametrize('value,max_length,expected', ((b'test1234', 8, b'test1234'), (b'test1234', 6, b'test12')))
def test_create_octet_string(value, max_length, expected):
    result = pdu.octet_string(value=value, _max=max_length)

    assert result == expected


def test_read_octet_string_none():
    result, index = pdu.read_octet_string(value=b'\x00', index=0, _max=1)

    assert result is None
    assert index == 1


@pytest.mark.parametrize('value,index,max_length,expected_value,expected_index', ((b'test1234', 0, 4, b'test', 4), (b'test1234', 2, 4, b'st12', 6)))
def test_read_octet_string(value, index, max_length, expected_value, expected_index):
    result, new_index = pdu.read_octet_string(value=value, index=index, _max=max_length)

    assert result == expected_value
    assert new_index == expected_index


def test_create_c_octet_string_none():
    result = pdu.c_octet_string(value=None)

    assert result == b'\x00'


@pytest.mark.parametrize('value,max_length,expected', (('test1234', 8, b'test123\x00'), ('test1234', 6, b'test1\x00')))
def test_create_c_octet_string(value, max_length, expected):
    result = pdu.c_octet_string(value=value, _max=max_length)

    assert result == expected


def test_read_c_octet_string_none():
    result, index = pdu.read_c_octet_string(value=b'\x00', index=0, _max=1)

    assert result is None
    assert index == 1


@pytest.mark.parametrize('value,index,max_length,expected_value,expected_index', ((b'tes\x001234', 0, 4, 'tes', 4), (b'test1\x0034', 2, 4, 'st1', 6)))
def test_read_c_octet_string(value, index, max_length, expected_value, expected_index):
    result, new_index = pdu.read_c_octet_string(value=value, index=index, _max=max_length)

    assert result == expected_value
    assert new_index == expected_index


def test_read_c_octet_string_fail():
    with pytest.raises(pdu.DecodeException):
        pdu.read_c_octet_string(value=b'test\x00', index=0, _max=1)


@pytest.mark.parametrize('value,octets,expected', (
        (None, 1, b'\x00'),
        (1, 1, b'\x01'),
        (1, 2, b'\x00\x01'),
        (1, 4, b'\x00\x00\x00\x01'),
        (1, 8, b'\x00\x00\x00\x00\x00\x00\x00\x01')
))
def test_create_integer(value, octets, expected):
    result = pdu.integer(value, octets)

    assert result == expected


def test_create_integer_fail():
    with pytest.raises(AttributeError):
        pdu.integer(value=3, octets=3)


@pytest.mark.parametrize('payload,octets,expected_value,expected_index', (
        (b'\x00', 1, 0, 1),
        (b'\x01', 1, 1, 1),
        (b'\x00\x01', 2, 1, 2),
        (b'\x00\x00\x00\x01', 4, 1, 4),
        (b'\x00\x00\x00\x00\x00\x00\x00\x01', 8, 1, 8)
))
def test_read_integer(payload, octets, expected_value, expected_index):
    result, index = pdu.read_integer(payload, 0, octets)

    assert result == expected_value
    assert index == expected_index


def test_read_tlv():
    payload = b'\x00\x01\x00\x03abc'

    tag, data, index = pdu.read_tlv(payload, index=0)

    assert tag == 1
    assert data == b'abc'
    assert index == len(payload)


def test_create_tlv():
    payload = pdu.create_tlv(1, b'abc')

    assert payload == b'\x00\x01\x00\x03abc'


def test_read_tlvs():
    tlv1 = b'\x00\x01\x00\x03abc'
    tlv2 = b'\x02\x0D\x00\x02\x00\x02'

    payload = tlv1 + tlv2

    result = pdu.read_tlvs(payload, index=0)

    assert pdu.TLV.sar_msg_ref_num in result
    assert result[pdu.TLV.sar_msg_ref_num] == 2
    assert 1 in result
    assert result[1] == b'abc'


def test_create_header():
    result = pdu.create_header(1, 3, 2)

    # Length without payload == 16 / 0x10
    assert result == b'\x00\x00\x00\x10\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x02'

    result = pdu.create_header(1, 3, 2, payload=b'abc')

    # Length without payload == 16 / 0x10
    assert result == b'\x00\x00\x00\x13\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x02abc'


def test_read_header():
    payload = b'\x00\x00\x00\x13\x00\x00\x00\x01\x00\x00\x00\x03\x00\x00\x00\x02abc'

    result = pdu.decode_header(payload)

    assert result['length'] == 19
    assert result['id'] == 1
    assert result['status'] == 3
    assert result['seq_no'] == 2
    assert result['payload'] == b'abc'
