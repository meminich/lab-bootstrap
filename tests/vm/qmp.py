"""Read-only VM observations and display capture over a fixture-local socket."""
import json
import socket


def read_reply(stream, request_id):
    while True:
        line = stream.readline()
        if not line:
            raise RuntimeError('QMP disconnected before its reply.')
        reply = json.loads(line)
        if reply.get('id') != request_id:
            continue  # Events can arrive between command replies.
        if 'error' in reply:
            raise RuntimeError('QMP error: ' + json.dumps(reply['error']))
        return reply['return']


def command(path, name, arguments=None):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(10)
        connection.connect(str(path))
        with connection.makefile('rwb') as stream:
            greeting = json.loads(stream.readline())
            if 'QMP' not in greeting:
                raise RuntimeError('Missing QMP greeting.')
            for request in ({'execute': 'qmp_capabilities', 'id': 0},
                            {'execute': name, 'arguments': arguments or {}, 'id': 1}):
                stream.write(json.dumps(request).encode() + b'\n')
                stream.flush()
                result = read_reply(stream, request['id'])
            return result
