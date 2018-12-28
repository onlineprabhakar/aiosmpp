import pytest

from aiosmpp import utils


def test_gsm_7_encode():
    source = 'Hello @ World £ and ]'

    # In GSM7
    # @ is 0x00
    # £ is 0x01
    # ] uses the ESC prefix of 0x1b and then \x3e would be converted from > to ]
    #   if they support the ESS prefix
    target = 'Hello \x00 World \x01 and \x1b\x3e'

    result = utils.gsm_encode(source)

    assert result == target


def test_gsm_7_strip():
    source = 'Hello World ∑'

    # The sigma character is stripped
    target = 'Hello World '

    result = utils.gsm_encode(source)

    assert result == target


def test_dlr_status_decode():
    payload = b'id:7220bb6bd0be98fa628de66590f80070 sub:001 dlvrd:001 submit date:0610190851' \
              b' done date:0610190951 stat:DELIVRD err:000 text:'

    result = utils.parse_dlr_text(payload)

    assert result['id'] == '7220bb6bd0be98fa628de66590f80070'
    assert result['sub'] == '001'
    assert result['dlvrd'] == '001'

    assert result['sdate'] == '0610190851'
    assert result['ddate'] == '0610190951'
    assert result['stat'] == 'DELIVRD'
    assert result['err'] == '000'
    assert result['text'] == ''


@pytest.mark.parametrize('payload', (
    'id:7220bb6bd0be98fa628de66590f80070 sub:001 dlvrd:001 submit date:0610190851 done date:0610190951 err:000 text:',
    'sub:001 dlvrd:001 submit date:0610190851 done date:0610190951 stat:DELIVRD err:000 text:',
    'sub:001 dlvrd:001 submit date:0610190851 done date:0610190951 err:000 text:'
))
def test_dlr_status_bad(payload):
    # As we have no ID and or no status, the result is useless
    result = utils.parse_dlr_text(payload)

    assert result is None
