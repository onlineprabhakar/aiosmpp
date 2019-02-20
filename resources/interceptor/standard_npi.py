import logging
import re

from aiosmpp.constants import AddrNPI, AddrTON
from aiosmpp.interceptor import lock_pdu_param


LONGCODE_REGEX = re.compile(r'^\d{7,}$')
SHORTCODE_REGEX = re.compile(r'^\d{1,7}$')


def process(event: dict, logger: logging.Logger) -> dict:

    number = event['pdus'][0]['source_addr']
    if LONGCODE_REGEX.match(number):
        npi = AddrNPI.ISDN
        ton = AddrTON.INTERNATIONAL
    elif SHORTCODE_REGEX.match(number):
        npi = AddrNPI.ISDN
        ton = AddrTON.UNKNOWN
    else:
        npi = AddrNPI.UNKNOWN
        ton = AddrTON.ALPHANUMERIC

    # Set TON/NPI on each pdu
    for pdu in event['pdus']:
        pdu['source_addr_npi'] = npi
        pdu['source_addr_ton'] = ton

    lock_pdu_param(event, 'source_addr_npi')
    lock_pdu_param(event, 'source_addr_ton')

    logger.info('Interceptor: {0}'.format(event))
    return event
