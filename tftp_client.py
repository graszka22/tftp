#!/usr/bin/env python3
import socket
import struct
import sys
import hashlib
HOST = 'localhost'
PORT = 6969
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.2)
filename = sys.argv[1]
initial_window_size = 64


def error(errcode, msg):
    sock.sendto(struct.pack("!HH%dsb" % len(msg), 5, errcode, msg, 0), (HOST, PORT))


def run():
    prevpack = struct.pack("!h%dsb5sb%dsb%dsb" % (len(filename), len('windowsize'), len(str(initial_window_size))),
                           1, filename.encode(), 0, b'octet', 0, b'windowsize', 0, str(initial_window_size).encode(), 0)
    global PORT
    sock.sendto(prevpack, (HOST, PORT))
    tries = 0
    window = 1
    while True:
        try:
            tries += 1
            pack, address = sock.recvfrom(1024)
            PORT = address[1]  # port mógł się zmienić
            opcode = struct.unpack("!H", pack[:2])[0]
            # paczka z oack prawdopodobnie się zgubiła i dochodzą nam dane
            # ignorujemy je
            if opcode == 3:
                continue
            # nastąpił błąd
            elif opcode == 5:
                errormsg = pack[4:-1].decode()
                print(errormsg)
                return
            # oack
            elif opcode == 6:
                opts = pack[2:].split(b'\0')
                if len(opts) != 3 or opts[0] != b'windowsize' or int(opts[1]) > initial_window_size:
                    error(8, b"bad option")
                    print("Error - bad oack")
                    return
                window = int(opts[1])
                # ack na zerowej paczce - ack oack
                prevpack = struct.pack("!hh", 4, 0)
                sock.sendto(prevpack, (HOST, PORT))
                break
            # serwer przysłał coś głupiego, ignorujemy...
            else:
                continue
        except socket.timeout:
            # próbowaliśmy 3 razy i serwer nie odpowiedział oack
            # może nie supportuje opcji w ogóle?
            if tries == 3:
                prevpack = struct.pack("!h%dsb5sb" % len(filename), 1, filename.encode(), 0, b'octet', 0)
                sock.sendto(prevpack, (HOST, PORT))
                break
            sock.sendto(prevpack, (HOST, PORT))
    m = hashlib.md5()
    packnum = 0
    eof = False
    while not eof:
        try:
            for i in range(window):
                pack, _ = sock.recvfrom(1024)
                opcode = struct.unpack("!H", pack[:2])[0]
                # data
                if opcode == 3:
                    data = struct.unpack("!HH%ds" % (len(pack)-4), pack)
                    # nie ten numer paczki co chcemy - pomijamy
                    if data[1] != (packnum+1) % (2**16):
                        i -= 1
                        continue
                    packnum = (packnum+1) % (2**16)
                    # print(data[2])
                    m.update(data[2])
                    prevpack = struct.pack("!HH", 4, packnum)
                    if len(data[2]) < 512:
                        eof = True
                        break
                # error
                elif opcode == 5:
                    errormsg = pack[4:-1].decode()
                    print(errormsg)
                    return
                # coś głupiego, może jakieś oack - pomijamy
                else:
                    continue
        except socket.timeout:
            sock.sendto(prevpack, (HOST, PORT))
        else:
            sock.sendto(prevpack, (HOST, PORT))
    print(m.hexdigest())

run()
sock.close()
