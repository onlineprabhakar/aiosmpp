import enum


class AddrTON(enum.IntEnum):
    UNKNOWN = 0x00
    INTERNATIONAL = 0x01
    NATIONAL = 0x02
    NETWORK_SPECIFIC = 0x03
    SUBSCRIBER_NUMBER = 0x04
    ALPHANUMERIC = 0x05
    ABBREVIATED = 0x06


class AddrNPI(enum.IntEnum):
    UNKNOWN = 0x00
    ISDN = 0x01
    DATA = 0x03
    TELEX = 0x04
    LAND_MOBILE = 0x06
    NATIONAL = 0x08
    PRIVATE = 0x09
    ERMES = 0x0a
    INTERNET = 0x0e
    WAP_CLIENT_ID = 0x1


class PriorityFlag(enum.IntEnum):
    LEVEL_0 = 0x00
    LEVEL_1 = 0x01
    LEVEL_2 = 0x02
    LEVEL_3 = 0x03


class RegisteredDeliveryReceipt(enum.IntEnum):
    NO_SMSC_DELIVERY_RECEIPT_REQUESTED = 0x00
    SMSC_DELIVERY_RECEIPT_REQUESTED = 0x01
    SMSC_DELIVERY_RECEIPT_REQUESTED_FOR_FAILURE = 0x02


class ReplaceIfPresentFlag(enum.IntEnum):
    DO_NOT_REPLACE = 0x00
    REPLACE = 0x01


class ESMClassMode(enum.IntEnum):
    DEFAULT = 0x0
    DATAGRAM = 0x1
    FORWARD = 0x2
    STORE_AND_FORWARD = 0x3


class ESMClassType(enum.IntEnum):
    DEFAULT = 0x00
    SMSC_DELIVERY_RECEIPT = 0x04
    DELIVERY_ACKNOWLEDGEMENT = 0x08
    MANUAL_ACKNOWLEDGMENT = 0x10
    CONVERSATION_ABORT = 0x18
    INTERMEDIATE_DELIVERY_NOTIFICATION = 0x20


class ESMClassGSMFeatures(enum.IntEnum):
    UDHI_INDICATOR_SET = 0x40
    SET_REPLY_PATH = 0x80


class MoreMessagesToSend(enum.IntEnum):
    NO_MORE_MESSAGES = 0x00
    MORE_MESSAGES = 0x01

