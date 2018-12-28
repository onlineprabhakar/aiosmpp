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
    SMSC_DELIVERY_RECEIPT = 0x08
    DELIVERY_ACKNOWLEDGEMENT = 0x10
    MANUAL_ACKNOWLEDGMENT = 0x20
    # CONVERSATION_ABORT = 0x18
    # INTERMEDIATE_DELIVERY_NOTIFICATION = 0x20


class ESMClassGSMFeatures(enum.IntEnum):
    UDHI_INDICATOR_SET = 0x40
    SET_REPLY_PATH = 0x80


class MoreMessagesToSend(enum.IntEnum):
    NO_MORE_MESSAGES = 0x00
    MORE_MESSAGES = 0x01


MESSAGE_STATE_SHORT = {
    'ENROUTE':       'ENROUTE',
    'DELIVERED':     'DELIVRD',
    'EXPIRED':       'EXPIRED',
    'DELETED':       'DELETED',
    'UNDELIVERABLE': 'UNDELIV',
    'ACCEPTED':      'ACCEPTD',
    'UNKNOWN':       'UNKNOWN',
    'REJECTED':      'REJECTD'
}


class MessageState(enum.IntEnum):
    ENROUTE = 1
    DELIVERED = 2
    EXPIRED = 3
    DELETED = 4
    UNDELIVERABLE = 5
    ACCEPTED = 6
    UNKNOWN = 7
    REJECTED = 8

    @property
    def short(self) -> str:
        return MESSAGE_STATE_SHORT[self.name]


class ESMClass(enum.IntFlag):
    MESSAGEING_MODE_DEFAULT = 0b00_0000_00
    MESSAGEING_MODE_DATAGRAM = 0b00_0000_01
    MESSAGEING_MODE_FORWARD = 0b00_0000_10
    MESSAGEING_MODE_STORE_AND_FORWARD = 0b00_0000_11

    MESSAGE_TYPE_DEFAULT = 0b00_0000_00
    MESSAGE_TYPE_CONTAINS_ACK = 0b00_0010_00
    MESSAGE_TYPE_CONTAINS_MANUAL_ACK = 0b00_0100_00

    GSM_FEATURES_NONE = 0b00_0000_00
    GSM_FEATURES_UDHI = 0b01_0000_00
    GSM_FEATURES_REPLY_PATH = 0b10_0000_00
    GSM_FEATURES_UDHI_AND_REPLY_PATH = 0b11_0000_00


class ESMClassInbound(enum.IntFlag):
    MESSAGE_TYPE_DEFAULT = 0b00_0000_00
    MESSAGE_TYPE_CONTAINS_DELIVERY_RECIPT = 0b00_0001_00
    MESSAGE_TYPE_CONTAINS_DELIVERY_ACK = 0b00_0010_00
    # 0b00_0011_00 # Reserved
    MESSAGE_TYPE_CONTAINS_MANUAL_ACK = 0b00_0100_00
    MESSAGE_TYPE_CONTAINS_CONVERSATION_ABORT = 0b00_0110_00
    MESSAGE_TYPE_CONTAINS_INTERMEDIATE_DELIVERY_NOTIFICATION = 0b00_1000_00

    GSM_FEATURES_NONE = 0b00_0000_00
    GSM_FEATURES_UDHI = 0b01_0000_00
    GSM_FEATURES_REPLY_PATH = 0b10_0000_00
    GSM_FEATURES_UDHI_AND_REPLY_PATH = 0b11_0000_00


class DataCoding(enum.IntFlag):
    SMSC_DEFAULT = 0b0000_0000
    IA5_ASCII = 0b0000_0001
    OCTET_UNSPECIFIED = 0b0000_0010
    LATIN_1 = 0b0000_0011
    OCTET_UNSPECIFIED_COMMON = 0b0000_0100
    JIS = 0b0000_0101
    CYRLLIC = 0b0000_0110
    ISO_8859_8 = 0b0000_0111
    UCS2 = 0b0000_1000
    PICTOGRAM = 0b0000_1001
    ISO_2202_JP = 0b0000_1010
    # 0b0000_1011 Reserved
    # 0b0000_1100 Reserved
    EXTENDED_KANJI_JIS = 0b0000_1101
    KS_C_5601 = 0b0000_1110
    # 0b0000_1111 Reserved
    # 0b1011_1111 Reserved
    GSM_MWI_1 = 0b1100_0000
    GSM_MWI_2 = 0b1101_0000
    # 0b1110_0000 Reserved
    GSM_MESSAGE_CONTROL = 0b1111_0000  # GSM_MESSAGE_CLASS

    @property
    def coding(self):
        if not hasattr(self, '_coding'):
            value = int(self) & 0b0000_1111
            self._coding = self.__class__(value).name
        return self._coding
