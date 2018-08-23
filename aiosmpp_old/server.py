import asyncio
import enum


class SMPPSessionState(enum.Enum):
    OPEN = enum.auto()  # Client connected, not yet issued bind #2.2
    BOUND_TX = enum.auto()  # Client connected and bound as TX
    BOUND_RX = enum.auto()  # Client connected and bound as RX
    BOUND_TRX = enum.auto()  # Client connected and bound as TRX
    CLOSED = enum.auto()  # Client as unbound and closed network connection


class SMPPServer(asyncio.Protocol):
    def __init__(self, *args, **kwargs):
        super(SMPPServer, self).__init__(*args, **kwargs)

        self.transport = None

        self.state = SMPPSessionState.CLOSED
        self.unacknowledged_requests = {}

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        print('Connection from {}'.format(peername))
        self.transport = transport

    def data_received(self, data):
        message = data.decode()
        print('Data received: {!r}'.format(message))

        print('Send: {!r}'.format(message))
        self.transport.write(data)

        print('Close the client socket')
        self.transport.close()










loop = asyncio.get_event_loop()
coro = loop.create_server(SMPPServer, '0.0.0.0', 8888)
server = loop.run_until_complete(coro)

# Serve requests until Ctrl+C is pressed
print('Serving on {}'.format(server.sockets[0].getsockname()))
try:
    loop.run_forever()
except KeyboardInterrupt:
    pass

# Close the server
server.close()
loop.run_until_complete(server.wait_closed())
loop.close()
