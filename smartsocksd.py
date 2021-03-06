#!/usr/bin/python

import socket
import select
import SocketServer
import struct
import logging

import config

def send_all(sock, data):
    bytes_sent = 0
    while True:
        r = sock.send(data[bytes_sent:])
        if r < 0:
            return r
        bytes_sent += r
        if bytes_sent == len(data):
            return bytes_sent


class ThreadingTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True

class Socks5Server(SocketServer.StreamRequestHandler):
    def handle_tcp(self, sock, remote):
        fdset = [sock, remote]
        while True:
            r, w, e = select.select(fdset, [], [])
            if sock in r:
                data = sock.recv(4096)
                if len(data) <= 0:
		    logging.error("read error from sock")
		    break
                elif send_all(remote, data) < len(data):
		    logging.error("send error to remote")
		    break
            if remote in r:
                data = remote.recv(4096)
                if len(data) <= 0:
		    logging.error("read error from remote, len = %i" % len(data))
		    break
                elif send_all(sock, data) < len(data):
		    logging.error("send error to sock")
		    break
    def handle(self):
        import isdirect
        try:
            sock = self.connection
            # 1. Version
            sock.recv(262)
            sock.sendall(b"\x05\x00");
            # 2. Request
            data = self.rfile.read(4)
            mode = ord(data[1])
            addrtype = ord(data[3])
            if addrtype == 1:       # IPv4
                addr = socket.inet_ntoa(self.rfile.read(4))
            elif addrtype == 3:     # Domain name
                addr = self.rfile.read(ord(sock.recv(1)[0]))
            port = struct.unpack('>H', self.rfile.read(2))
            reply = b"\x05\x00\x00\x01"
            try:
                if mode == 1:  # 1. Tcp connect
                    remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    if isdirect.isdirect(addr):
                        logging.info('direct connect to %s:%d', addr, port[0])
                        remote.connect((addr, port[0]))
                        local = remote.getsockname()
                        reply += socket.inet_aton(local[0]) + struct.pack(">H", local[1])
                    else:
                        logging.info('parent connect to %s:%d', addr, port[0])
                        remote.connect((config.PARENT_ADDRESS, config.PARENT_PORT))
                        local = remote.getsockname()
                        reply += socket.inet_aton(local[0]) + struct.pack(">H", local[1])
                        remote.sendall(b"\x05\x01\x00")
                        data = remote.recv(262)
                        if addrtype == 1:
			    tosend = b"\x05\x01\x00\x01" + socket.inet_aton(addr)
                        elif addrtype == 3:
			    tosend = b"\x05\x01\x00\x03"+struct.pack('B', len(addr)) + bytes(addr)
			tosend += struct.pack('>H', port[0])
			logging.debug("sending %s" %tosend)
                        remote.sendall(tosend)
                        data = remote.recv(262)
			logging.debug("data len: %i content %s", len(data), repr(data))
                else:
                    reply = b"\x05\x07\x00\x01" # Command not supported
            except socket.error:
                # Connection refused
                reply = '\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00'
            sock.sendall(reply)
            # 3. Transfering
            if reply[1] == '\x00':  # Success
                if mode == 1:    # 1. Tcp connect
                    self.handle_tcp(sock, remote)
        except socket.error,e:
            logging.error('socket error %s', e)
	except Exception,e:
	    logging.error('unexpectedd error %s', e)
def main():
    logging.basicConfig(level=logging.DEBUG, filename = "/tmp/smartproxy.log")
    server = ThreadingTCPServer(('', config.PORT), Socks5Server)
    server.serve_forever()

if __name__ == '__main__':
    main()

