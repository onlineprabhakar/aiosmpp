from aiosmpp import constants as const


def test_short_data_coding():

    coding_1 = const.DataCoding(0b0101_0001)

    # 0b01010001 & 0b00001111 = 0b00000001 = IA5_ASCII
    assert coding_1.coding == const.DataCoding(0b00000001).name


def test_short_message_state():
    undeliverable = const.MessageState(5)

    assert undeliverable.short == const.MESSAGE_STATE_SHORT['UNDELIVERABLE']
