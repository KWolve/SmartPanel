# -*- coding: utf-8 -*-
"""PC 冒充小程序给面板发一张图/一个视频，用于验收「相册上传」链路（无需真小程序）。

协议（与 components/mp_transfer 一致）：
  发现：UDP 8899 收广播正文 `zkswe:<设备名>` -> 拿到设备 IP
  传输：TCP 9000；包 = type(1B) + fileLen(4B BE) + nameLen(2B BE) + filename(UTF-8) + data
        32 KiB 分块，非末块回 `ACK <累计字节>\\n`，末块校验改名后回 `OK\\n`
        type: 1=图片 2=视频

用法：
  python projects/SmartPanel_HA/tools/mp_send_test.py --file D:\\pic.jpg
  python projects/SmartPanel_HA/tools/mp_send_test.py --file test.mp4 --device-name 智能面板
  python projects/SmartPanel_HA/tools/mp_send_test.py --discover        # 只看广播能不能发现设备
"""

import argparse
import os
import socket
import struct
import sys
import time

BCAST_PORT = 8899
TCP_PORT = 9000
CHUNK = 32 * 1024
IMG_EXT = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'}
VID_EXT = {'.mp4', '.avi', '.mkv', '.mov', '.3gp'}


def discover(timeout=8.0, want=None):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', BCAST_PORT))
    s.settimeout(timeout)
    print('监听 UDP %d 上的设备广播…（设备需停在「相册上传」页）' % BCAST_PORT)
    t0 = time.time()
    found = []
    while time.time() - t0 < timeout:
        try:
            data, addr = s.recvfrom(512)
        except socket.timeout:
            break
        txt = data.decode('utf-8', 'replace')
        name = txt[6:] if txt.startswith('zkswe:') else txt
        if not any(a == addr[0] for a, _ in found):
            found.append((addr[0], name))
            print('  发现设备: %s  名称=%s' % (addr[0], name))
            if want and name.strip() == want:
                s.close()
                return addr[0], name
    s.close()
    if found:
        return found[0][0], found[0][1]
    return None, None


def send_file(ip, path, timeout=20.0):
    ext = os.path.splitext(path)[1].lower()
    if ext in IMG_EXT:
        ftype = 1
    elif ext in VID_EXT:
        ftype = 2
    else:
        ftype = 3
    name = os.path.basename(path).encode('utf-8')
    size = os.path.getsize(path)
    print('发送: %s  type=%d  size=%d B  -> %s:%d' % (path, ftype, size, ip, TCP_PORT))

    c = socket.create_connection((ip, TCP_PORT), timeout=timeout)
    c.settimeout(timeout)
    head = struct.pack('>BIH', ftype, size, len(name)) + name
    c.sendall(head)

    sent = 0
    with open(path, 'rb') as f:
        while True:
            buf = f.read(CHUNK)
            if not buf:
                break
            c.sendall(buf)
            sent += len(buf)
            if sent < size:
                ack = c.recv(64)
                if not ack.startswith(b'ACK'):
                    print('  意外应答: %r（期望 ACK）' % ack)
                    c.close()
                    return False
            else:
                resp = b''
                t0 = time.time()
                while time.time() - t0 < timeout:
                    part = c.recv(64)
                    if not part:
                        break
                    resp += part
                    if b'OK' in resp:
                        break
                print('  末块应答: %r' % resp)
                c.close()
                return b'OK' in resp
    c.close()
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file')
    ap.add_argument('--ip', help='跳过发现，直连该 IP')
    ap.add_argument('--device-name', default=None, help='只认这个名字的设备')
    ap.add_argument('--discover', action='store_true')
    ap.add_argument('--timeout', type=float, default=8.0)
    a = ap.parse_args()

    ip = a.ip
    if not ip:
        ip, name = discover(a.timeout, a.device_name)
        if not ip:
            print('没发现设备（检查：设备是否停在「相册上传」页 / 同一局域网 / 防火墙允许 UDP 8899）')
            return 2
    if a.discover and not a.file:
        print('发现 OK: %s' % ip)
        return 0
    if not a.file:
        print('需要 --file')
        return 2
    ok = send_file(ip, a.file)
    print('结果: %s' % ('OK（设备已回 OK）' if ok else 'FAIL'))
    return 0 if ok else 3


if __name__ == '__main__':
    sys.exit(main())
