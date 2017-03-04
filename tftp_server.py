#!/usr/bin/env python3
import socket
import struct
from threading import Thread

HOST = 'localhost'
PORT = 6969
initial_window_size = 64
timeout = 0.2


def error(sock, addr, errcode, msg):
    sock.sendto(struct.pack("!HH%dsb" % len(msg), 5, errcode, msg, 0), addr)


class ClientThread(Thread):
    def __init__(self, data, addr):
        super().__init__()
        self.data = data
        self.addr = addr

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.bind(('', 0))  # pozwalamy systemowi wybrać jakiś wolny port
        opcode = struct.unpack("!H", self.data[:2])[0]
        if opcode != 1:
            error(sock, self.addr, 4, b"Illegal TFTP operation")
            return
        opts = self.data[2:].split(b'\0')
        filename = opts[0].decode()
        windowsize = 1
        packnum = 0
        eof = False
        queue = []
        try:
            f = open(filename, 'rb')
        except:
            error(sock, self.addr, 1, b"File not found.")
        else:
            for i in range(2, len(opts), 2):
                if opts[i] == b"windowsize":
                    windowsize = min(int(opts[i+1]), initial_window_size)
                    pack = struct.pack("!H%dsb%dsb" % (len("windowsize"), len(str(windowsize))),
                                       6, b"windowsize", 0, str(windowsize).encode(), 0)
                    sock.sendto(pack, self.addr)
                    tries = 0
                    # czekamy na ACK 0 od klienta
                    while True:
                        try:
                            pack = sock.recv(512)
                            tries = 0
                            if pack == b"\x00\x04\x00\x00":
                                break
                            # error
                            if struct.unpack('!H', pack[:2])[0] == 5:
                                return
                        except socket.timeout:
                            tries += 1
                            # 10 razy próbowaliśmy dostać jakąś wiadomość i nie udało nam się czegokolwiek dostać
                            # prawdopodobnie z klientem coś się stało
                            # kończymy wątek i wyślemy mu ładnego errora w razie czego
                            if tries == 10:
                                error(sock, self.addr, 0, b"Timeout")
                                return
                            sock.sendto(pack, self.addr)
            tries = 0
            while not eof or len(queue) > 0:
                # wysyłamy co jeszcze nie zostało ack-owane z kolejki
                for w in queue:
                    sock.sendto(w[1], self.addr)
                # i dokładamy żeby mieć pełne okienko
                for i in range(packnum+1+len(queue), packnum + windowsize + 1):
                    data = f.read(512)
                    pack = struct.pack("!HH%ds" % len(data), 3, i % (2 ** 16), data)
                    sock.sendto(pack, self.addr)
                    queue.append((i % (2 ** 16), pack))
                    if len(data) < 512:
                        eof = True
                        break
                while True:
                    try:
                        data2 = sock.recv(512)
                        tries = 0
                        opc = int(struct.unpack("!H", data2[:2])[0])
                        if opc == 4:  # ack
                            packnum = int(struct.unpack("!HH", data2)[1])
                            # szukamy paczki o tym numerze w kolejce
                            for x in queue:
                                if x[0] == packnum:
                                    break
                            # jeżeli nie ma takiej paczki to jest to jakiś stary, nic nie wnoszący ack
                            # pomijamy go
                            else:
                                continue
                            # usuwamy wszystkie paczki z kolejki które zostały ack-owane
                            while queue[0][0] != packnum:
                                queue.pop(0)
                            queue.pop(0)
                            break
                        elif opc == 5:
                            return
                        # jakaś błędna paczka
                        else:
                            continue
                    except socket.timeout:
                        tries += 1
                        # jw
                        if tries == 10:
                            error(sock, self.addr, 0, b"Timeout")
                            return
                        break
        sock.close()


def run():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    while True:
        data, addr = sock.recvfrom(512)
        ClientThread(data, addr).start()
run()
