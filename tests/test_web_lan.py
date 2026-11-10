import unittest
from coc_bot.web.network import physical_lan_addresses,advertised_urls,is_lan_ip


class LanAddressTests(unittest.TestCase):
    def test_only_active_private_physical_addresses_are_advertised(self):
        def interface(name,address,up=True):
            return {'ifname':name,'flags':['UP'] if up else [],
                    'addr_info':[{'family':'inet','local':address}]}
        data=[interface('wlp3s0','192.168.0.121'),interface('docker0','172.17.0.1'),
              interface('tailscale0','100.82.13.84'),interface('happ-xray','172.19.0.1'),
              interface('eno1','10.0.0.10',False),interface('public','8.8.8.8')]
        result=physical_lan_addresses(data,lambda name:name in ('wlp3s0','eno1','public'))
        self.assertEqual(result,['192.168.0.121'])

    def test_phone_links_exclude_loopback_and_public_origins(self):
        result=advertised_urls(['http://localhost:8765','http://127.0.0.1:8765',
                                'http://192.168.0.121:8765','https://8.8.8.8','http://evil.invalid'])
        self.assertEqual(result,['http://192.168.0.121:8765'])

    def test_no_wildcard_link_local_or_multicast_is_a_lan_target(self):
        for value in ('0.0.0.0','169.254.1.2','224.0.0.1','100.82.13.84','::1','not-an-address'):
            with self.subTest(value=value):self.assertFalse(is_lan_ip(value))
