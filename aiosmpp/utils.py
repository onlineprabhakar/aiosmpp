GSM_CHARS = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>"
             "?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM_CHARS_EXT = ("````````````````````^```````````````````{}`````\\````````````[~]`"
                 "|````````````````````````````````````€``````````````````````````")


def gsm_encode(plaintext: str) -> str:
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
