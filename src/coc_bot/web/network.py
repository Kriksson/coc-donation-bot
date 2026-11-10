"""Explicit local-network listeners; virtual/VPN interfaces are not advertised."""
from contextlib import contextmanager
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
from urllib.parse import urlparse


_LAN = tuple(ipaddress.ip_network(value) for value in
             ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))


def is_lan_ip(value):
    try:
        address=ipaddress.ip_address(value)
        return address.version==4 and any(address in network for network in _LAN)
    except ValueError:
        return False


def physical_lan_addresses(interfaces, physical=None):
    physical=physical or (lambda name:(Path('/sys/class/net')/name/'device').exists())
    result=[]
    for interface in interfaces:
        name=interface.get('ifname','')
        if 'UP' not in interface.get('flags',[]) or not physical(name):continue
        for info in interface.get('addr_info',[]):
            value=info.get('local','')
            if info.get('family')=='inet' and is_lan_ip(value) and value not in result:
                result.append(value)
    return result


def discover_lan_addresses():
    try:
        result=subprocess.run(['ip','-j','-4','address','show','scope','global'],
                              capture_output=True,text=True,timeout=3,check=True)
        return physical_lan_addresses(json.loads(result.stdout))
    except (OSError,ValueError,subprocess.SubprocessError):
        return []


def advertised_urls(origins):
    return sorted(origin for origin in origins
                  if urlparse(origin).scheme in ('http','https')
                  and is_lan_ip(urlparse(origin).hostname or ''))


@contextmanager
def listening_sockets(addresses,port):
    sockets=[]
    try:
        for address in addresses:
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            sockets.append(listener)
            listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            listener.bind((address,port))
            listener.listen(128)
            listener.setblocking(False)
        yield sockets
    finally:
        for listener in sockets:listener.close()
