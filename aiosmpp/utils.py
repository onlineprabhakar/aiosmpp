import re
from urllib.parse import urlparse
from typing import Union, Dict, Tuple

GSM_CHARS = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>"
             "?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM_CHARS_EXT = ("````````````````````^```````````````````{}`````\\````````````[~]`"
                 "|````````````````````````````````````€``````````````````````````")


def gsm_encode(plaintext: str) -> str:  # noqa: E501
    """Will encode plaintext to gsm 338
    Taken from
    http://stackoverflow.com/questions/2452861/python-library-for-converting-plain-text-ascii-into-gsm-7-bit-character-set
    """
    res = ""
    for c in plaintext:
        idx = GSM_CHARS.find(c)
        if idx != -1:
            res += chr(idx)
            continue
        idx = GSM_CHARS_EXT.find(c)
        if idx != -1:
            res += chr(27) + chr(idx)
    return res


DLR_PATTERNS = (
    re.compile(r"id:(?P<id>[\dA-Za-z-_]+)"),
    re.compile(r"sub:(?P<sub>\d{3})"),
    re.compile(r"dlvrd:(?P<dlvrd>\d{3})"),
    re.compile(r"submit date:(?P<sdate>\d+)"),
    re.compile(r"done date:(?P<ddate>\d+)"),
    re.compile(r"stat:(?P<stat>\w{7})"),
    re.compile(r"err:(?P<err>\w{3})"),
    re.compile(r"text:(?P<text>.*)"),
)


def parse_dlr_text(dlr_text: Union[str, bytes]) -> Union[Dict[str, str], None]:
    if isinstance(dlr_text, bytes):
        dlr_text = dlr_text.decode(errors='ignore')

    # DLR text is str now.
    # DLR text parsing lifted from
    # https://github.com/jookies/jasmin/blob/master/jasmin/protocols/smpp/operations.py - credit to them

    # DLR Format
    # Example of DLR content
    # id:IIIIIIIIII sub:SSS dlvrd:DDD submit date:YYMMDDHHMM done date:YYMMDDHHMM stat:ZZZZZZZ err:YYY text:
    result = {
        'dlvrd': 'ND',
        'sub': 'ND',
        'sdate': 'ND',
        'ddate': 'ND',
        'err': 'ND',
        'text': ''
    }

    for pattern in DLR_PATTERNS:
        match = pattern.search(dlr_text)
        if match:
            key = list(match.groupdict().keys())[0]
            # Update id and stat only once
            if key not in ('id', 'stat') or (key == 'id' and 'id' not in result) or \
                    (key == 'stat' and 'stat' not in result):
                result.update(match.groupdict())

    # Only return result if we have decent details
    if 'id' in result and 'stat' in result:
        return result
    return None


def s3_url_parse(url: str) -> Tuple[str, str]:
    result = urlparse(url)

    return result.netloc, result.path.lstrip('/')
