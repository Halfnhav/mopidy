"""
This is our MPD server implementation.
"""

import asynchat
import asyncore
import logging
import multiprocessing
import socket
import sys

from mopidy import get_mpd_protocol_version, settings
from mopidy.mpd import MpdAckError
from mopidy.utils import indent, pickle_connection

logger = logging.getLogger('mopidy.mpd.server')

#: The MPD protocol uses UTF-8 for encoding all data.
ENCODING = u'utf-8'

#: The MPD protocol uses ``\n`` as line terminator.
LINE_TERMINATOR = u'\n'

class MpdServer(asyncore.dispatcher):
    """
    The MPD server. Creates a :class:`MpdSession` for each client connection.
    """

    def __init__(self, core_queue):
        asyncore.dispatcher.__init__(self)
        self.core_queue = core_queue
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind((settings.SERVER_HOSTNAME, settings.SERVER_PORT))
        self.listen(1)
        logger.info(u'Please connect to %s port %s using an MPD client.',
            settings.SERVER_HOSTNAME, settings.SERVER_PORT)

    def handle_accept(self):
        (client_socket, client_address) = self.accept()
        logger.info(u'Connection from: [%s]:%s', *client_address)
        MpdSession(self, client_socket, client_address, self.core_queue)

    def handle_close(self):
        self.close()


class MpdSession(asynchat.async_chat):
    """
    The MPD client session. Dispatches MPD requests to the frontend.
    """

    def __init__(self, server, client_socket, client_address, core_queue):
        asynchat.async_chat.__init__(self, sock=client_socket)
        self.server = server
        self.client_address = client_address
        self.core_queue = core_queue
        self.input_buffer = []
        self.set_terminator(LINE_TERMINATOR.encode(ENCODING))
        self.send_response(u'OK MPD %s' % get_mpd_protocol_version())

    def collect_incoming_data(self, data):
        self.input_buffer.append(data)

    def found_terminator(self):
        data = ''.join(self.input_buffer).strip()
        self.input_buffer = []
        input = data.decode(ENCODING)
        logger.debug(u'Input: %s', indent(input))
        self.handle_request(input)

    def handle_request(self, input):
        my_end, other_end = multiprocessing.Pipe()
        self.core_queue.put({
            'command': 'mpd_request',
            'request': input,
            'reply_to': pickle_connection(other_end),
        })
        my_end.poll(None)
        response = my_end.recv()
        if response is not None:
            self.handle_response(response)

    def handle_response(self, response):
        self.send_response(LINE_TERMINATOR.join(response))

    def send_response(self, output):
        logger.debug(u'Output: %s', indent(output))
        output = u'%s%s' % (output, LINE_TERMINATOR)
        data = output.encode(ENCODING)
        self.push(data)
