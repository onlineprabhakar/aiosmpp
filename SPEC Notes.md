# acronyms
SMSC (smpp server)
ESME (smpp client)

# outbind #2.2.1
The _outbind_ op allows the SMSC to tell an ESME to originate a `bind_receiver` request. Can be initiated by the SMSC initiating a connection
to the ESME.

If the ESME doesnt like this, it should close the connection

```
ESME                SMSC
| <- outbind ------------ |
|                         |
| -- bind_receiver -----> | 
|                         | 
| <- bind_receiver_resp - |
|                         |
| <- deliver_sm --------- |
|                         |
| -- deliver_sm_resp ---> |
```

# SMPP PDU Summary

```
PDU                        Required State       Issued by ESME  Issued by SMSC
bind_transmitter           OPEN                 Yes             No
bind_transmitter_resp      OPEN                 No              Yes
bind_receiver              OPEN                 Yes             No
bind_receiver_resp         OPEN                 No              Yes
bind_transceiver           OPEN                 Yes             No
bind_transceiver_resp      OPEN                 No              Yes
outbind                    OPEN                 No              Yes
unbind                     BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
unbind_resp                BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
submit_sm                  BOUND_TX,TRX         Yes,Yes        No,No
submit_sm_resp             BOUND_TX,TRX         No,No          Yes,Yes
submit_sm_multi            BOUND_TX,TRX         Yes,Yes        No,No
submit_sm_multi_resp       BOUND_TX,TRX         No,No          Yes,Yes
data_sm                    BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
data_sm_resp               BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
deliver_sm                 BOUND_RX,TRX         No,No          Yes,Yes
deliver_sm_resp            BOUND_RX,TRX         Yes,Yes        No,No
query_sm                   BOUND_TX,TRX         Yes,Yes        No,No
query_sm_resp              BOUND_TX,TRX         No,No          Yes,Yes
cancel_sm                  BOUND_TX,TRX         Yes,Yes        No,No
cancel_sm_resp             BOUND_TX,TRX         No,No          Yes,Yes
replace_sm                 BOUND_TX             Yes            No
replace_sm_resp            BOUND_TX             No             Yes
enquire_link               BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
enquire_link_resp          BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
alert_notification         BOUND_RX,TRX         No,No          Yes,Yes           - no response
generic_nack               BOUND_TX,RX,TRX      Yes,Yes,Yes    Yes,Yes,Yes
```

# Info

ESME should return SMPP responses to the SMSC in the same order in which the original requests were received.
The only relevant PDU response that an ESME Transmitter returns in a transmitter session is an `enquire_link_resp`

Session Initiation timer to ensure when an ESME inititates na SMPP session that this occurs within a specified period
Timer for enquire link
Inactivity timer for inactive period of NO messages
transaction timer, timelapse between request and response

Store and forward mode - smsc stores msg
Datagram message mode - think udp, spams messages, doesnt care about delivery
Transaction message mode - waits till sent to return resp

# Types

Integer - unsigned, MSB first, big endian
C-Octet String - Series of ASCII, NULL terminated
C-Octet String Decimal - ASCII characters representing a decimal digit 0-9, NULL terminated
C-Octet String Hex - ASCII characters representing a hexadecimal digit 0-F, NULL terminated
Octet String - Series of octets, not necessarily NULL terminated

# PDU Format

command length - 4octet integer - total length including length field
command id - 4octet integer - command ID
command status - 4octet integer - only relevant in response, must be null in request
sequence number - 4octet integer - increased per request, preserved in response
manditory params - var mixed
optional params - var mixed

## E.g. bind_transmitter

0000002F000000020000000000000001534D50503354455354007365637265743038005355424D4954310000010100

The header would be decoded as follows:
    
    00 00 00 2F Command Length 0x0000002F
    00 00 00 02 Command ID 0x00000002 (bind_transmitter)
    00 00 00 00 Command Status 0x00000000
    00 00 00 01 Sequence Number 0x00000001
    
The remaining data represents the PDU body (which in this example relates to the
bind_transmitter PDU)

# Optional param format (TLV)

Tag - 2octet integer
Length - 2octet integer
Value - variable