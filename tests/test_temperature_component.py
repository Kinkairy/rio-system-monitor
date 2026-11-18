import json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from rio_monitor.temperature_component import TemperatureComponent,read_status

class TemperatureTests(unittest.TestCase):
    def test_status_requires_fresh_valid_cpu_temperature(self):
        with tempfile.TemporaryDirectory() as directory:
            file=Path(directory)/'status.json'
            row=dict(version=1,timestamp=100,status='ready',cpu_temperature=58)
            file.write_text(json.dumps(row));self.assertEqual(read_status(file,102)['cpu_temperature'],58)
            self.assertIsNone(read_status(file,106));self.assertIsNone(read_status(file,99))
            for value in (True,-1,200,None):
                row['cpu_temperature']=value;file.write_text(json.dumps(row));self.assertIsNone(read_status(file,102)['cpu_temperature'])
            file.write_text('[]');self.assertIsNone(read_status(file,102))
    def test_old_service_waits_for_a_click_and_never_displays_a_margin(self):
        component=TemperatureComponent(Path(),start=False)
        legacy=dict(status='ready',cpu_temperature=69)
        corrected=dict(status='ready',cpu_temperature=47,sensor='CPU Package')
        def update(helper,stop):
            stop.set();component.wake.set()
            return 'installed'
        component.updater=Mock(side_effect=update)
        with patch('rio_monitor.temperature_component.service_installed',return_value=True), patch('rio_monitor.temperature_component.read_status',side_effect=[legacy,corrected]):
            component.poll()
            self.assertIsNone(component.temperature())
            self.assertTrue(component.snapshot()['update_available'])
            component.updater.assert_not_called()
            component.request_update();component.request_update()
            self.assertEqual(component.snapshot()['state'],'updating')
            component.run()
        component.updater.assert_called_once()
        self.assertEqual(component.temperature(),47)
        self.assertFalse(component.snapshot()['update_available'])

    def test_declined_component_update_can_be_retried(self):
        component=TemperatureComponent(Path(),start=False)
        def decline(helper,stop):
            stop.set();component.wake.set()
            return 'cancelled'
        component.updater=decline
        with patch('rio_monitor.temperature_component.service_installed',return_value=True), patch('rio_monitor.temperature_component.read_status',return_value=dict(status='ready',cpu_temperature=68)):
            component.poll();component.request_update();component.run()
        self.assertEqual(component.snapshot()['state'],'update_cancelled')
        self.assertTrue(component.enabled)
        self.assertTrue(component.update_available)
        self.assertIsNone(component.temperature())

    def test_new_unsupported_and_external_sources_do_not_prompt_upgrade(self):
        component=TemperatureComponent(Path(),start=False)
        with patch('rio_monitor.temperature_component.service_installed',return_value=True), patch('rio_monitor.temperature_component.read_status',return_value=dict(status='unsupported',cpu_temperature=None,sensor=None)):
            component.poll()
            self.assertFalse(component.update_available)
        with patch('rio_monitor.temperature_component.service_installed',return_value=False), patch.object(component,'probe_existing',return_value=dict(cpu_temperature=53,source='existing')):
            component.poll();component.request_update()
            self.assertFalse(component.update_requested)
            self.assertEqual(component.temperature(),53)

    def test_startup_never_requests_installation(self):
        installer=Mock();component=TemperatureComponent(Path(),installer=installer,start=False)
        with patch('rio_monitor.temperature_component.service_installed',return_value=False),patch.object(component,'probe_existing',return_value=None):component.poll()
        self.assertEqual(component.state,'missing');installer.assert_not_called();self.assertFalse(component.snapshot()['checked'])
    def test_existing_interface_avoids_installation(self):
        installer=Mock();component=TemperatureComponent(Path(),installer=installer,start=False)
        with patch('rio_monitor.temperature_component.service_installed',return_value=False),patch.object(component,'probe_existing',return_value=dict(cpu_temperature=61,source='existing monitor')):component.poll()
        self.assertEqual(component.temperature(),61);self.assertTrue(component.snapshot()['checked']);installer.assert_not_called()
    def test_off_schedules_explicit_removal_and_blocks_reenable_while_busy(self):
        component=TemperatureComponent(Path(),start=False);component.installed=True;component.state='ready'
        with patch('rio_monitor.temperature_component.write_enabled') as write:
            component.request(False);self.assertFalse(component.enabled);self.assertTrue(component.uninstall_requested)
            self.assertEqual(component.snapshot()['state'],'uninstalling')
            component.request(True);self.assertFalse(component.enabled);self.assertFalse(component.install_requested)
            write.assert_called_once_with(False)
    def test_removal_success_disables_our_service(self):
        component=TemperatureComponent(Path(),start=False);component.installed=True;component.state='ready'
        def remove(helper,stop):stop.set();component.wake.set();return 'uninstalled'
        component.uninstaller=Mock(side_effect=remove)
        with patch('rio_monitor.temperature_component.write_enabled'),patch('rio_monitor.temperature_component.service_installed',return_value=False):
            component.request(False);component.run()
        self.assertFalse(component.installed);self.assertFalse(component.enabled);self.assertEqual(component.state,'removed');component.uninstaller.assert_called_once()
    def test_cancelled_removal_restores_enabled_control(self):
        component=TemperatureComponent(Path(),start=False);component.installed=True;component.state='ready'
        def cancel(helper,stop):stop.set();component.wake.set();return 'cancelled'
        component.uninstaller=cancel
        with patch('rio_monitor.temperature_component.write_enabled') as write,patch('rio_monitor.temperature_component.service_installed',return_value=True):
            component.request(False);component.run()
        self.assertTrue(component.installed);self.assertTrue(component.enabled);self.assertEqual(component.state,'cancelled')
        self.assertEqual([c.args[0] for c in write.call_args_list],[False,True])
    def test_external_interface_is_read_only_and_never_removed(self):
        installer=Mock();uninstaller=Mock();component=TemperatureComponent(Path(),start=False,installer=installer,uninstaller=uninstaller)
        with patch('rio_monitor.temperature_component.service_installed',return_value=False),patch.object(component,'probe_existing',return_value=dict(cpu_temperature=61,source='existing monitor')):
            component.poll();component.request(False)
        self.assertTrue(component.snapshot()['external']);self.assertTrue(component.enabled)
        self.assertEqual(component.temperature(),61);self.assertFalse(component.uninstall_requested);installer.assert_not_called();uninstaller.assert_not_called()
    def test_external_sensor_is_discovered_even_when_our_component_is_off(self):
        component=TemperatureComponent(Path(),enabled=False,start=False);component.note_native(55)
        with patch('rio_monitor.temperature_component.service_installed',return_value=False):component.poll()
        self.assertTrue(component.snapshot()['external']);self.assertTrue(component.enabled);self.assertEqual(component.temperature(),55)
    def test_disable_write_failure_rolls_back(self):
        component=TemperatureComponent(Path(),start=False);component.installed=True;component.state='ready'
        with patch('rio_monitor.temperature_component.write_enabled',side_effect=OSError('Access denied')):component.request(False)
        self.assertTrue(component.enabled);self.assertEqual(component.state,'error')
    def test_delayed_service_disable_status_does_not_cancel_enable_action(self):
        component=TemperatureComponent(Path(),start=False);component.installed=True;component.state='off';component.enabled=False
        row=dict(status='disabled',cpu_temperature=None)
        with patch('rio_monitor.temperature_component.write_enabled'),patch('rio_monitor.temperature_component.read_status',return_value=row),patch('rio_monitor.temperature_component.service_installed',return_value=True):
            component.request(True);component.poll();self.assertTrue(component.enabled);self.assertEqual(component.state,'starting')
    def test_reading_expires_and_disabled_never_returns_previous_temperature(self):
        component=TemperatureComponent(Path(),start=False);component.value=58;component.stamp=time.monotonic();self.assertEqual(component.temperature(),58)
        component.stamp-=6;self.assertIsNone(component.temperature());component.stamp=time.monotonic();component.request(False);self.assertIsNone(component.temperature())
    def test_cancelled_admin_prompt_restores_switch_and_preserves_failure_status(self):
        component=TemperatureComponent(Path(),start=False)
        def cancel(helper,stop):stop.set();component.wake.set();return 'cancelled'
        component.installer=cancel;component.request(True)
        with patch('rio_monitor.temperature_component.service_installed',return_value=False),patch.object(component,'probe_existing',return_value=None):component.run()
        self.assertFalse(component.enabled);self.assertFalse(component.snapshot()['checked']);self.assertEqual(component.state,'cancelled')
        with patch('rio_monitor.temperature_component.service_installed',return_value=False):component.poll()
        self.assertEqual(component.state,'cancelled')
