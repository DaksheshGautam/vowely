import unittest
from types import SimpleNamespace
from localflow.devices import microphones


class DevicesTests(unittest.TestCase):
    def source(self):
        hosts = [{'name': 'MME'}, {'name': 'Windows WASAPI'}, {'name': 'Windows WDM-KS'}]
        devices = [
            dict(name='Microphone Array (Built-in Au',hostapi=0,max_input_channels=1),
            dict(name='Microphone Array (Built-in Audio)',hostapi=1,max_input_channels=2),
            dict(name='Headset (External)',hostapi=0,max_input_channels=1),
            dict(name='Headset (External)',hostapi=1,max_input_channels=1),
            dict(name='Stereo Mix (Built-in)',hostapi=1,max_input_channels=2),
            dict(name='Old disconnected headset',hostapi=2,max_input_channels=1),
            dict(name='Microsoft Sound Mapper - Input',hostapi=0,max_input_channels=1)]
        def check(**kwargs):
            if kwargs['device'] == 1:
                raise ValueError('WASAPI endpoint requires another sample rate')
        return SimpleNamespace(query_devices=lambda:devices,query_hostapis=lambda:hosts,check_input_settings=check)

    def test_basic_list_has_one_route_per_current_microphone(self):
        result = microphones(self.source())
        self.assertEqual([(d.name,d.index) for d in result],
                         [('Microphone Array (Built-in Audio)',0),('Headset (External)',3)])

    def test_saved_compatible_interface_is_preserved(self):
        result = microphones(self.source(),selected=2)
        self.assertEqual(result[1].index,2)

    def test_raw_inputs_are_only_in_advanced_view(self):
        result = microphones(self.source(),advanced=True)
        self.assertEqual(len(result),7)
        self.assertIn('Windows WDM-KS',result[5].name)
