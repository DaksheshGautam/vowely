import unittest
from unittest.mock import Mock

from localflow.probe import FocusProbe
from localflow.config import Config
from localflow.policy import Target


class ProbeTests(unittest.TestCase):
    def test_hung_correction_read_is_also_bounded(self):
        probe = FocusProbe()
        probe.start = Mock()
        probe.ready = True
        process,connection = Mock(),Mock()
        process.is_alive.return_value = True
        connection.poll.return_value = False
        probe.process,probe.connection = process,connection
        target = Target(1,2,'editor.exe',(1,2),'','Editor',False,True)
        self.assertIsNone(probe.correction_span(target,Config(),'Meet Jan.'))
        connection.poll.assert_called_once_with(.35)
        process.terminate.assert_called_once()

    def test_hung_provider_is_terminated_and_returns_unknown(self):
        probe = FocusProbe()
        probe.start = Mock()
        probe.ready = True
        process, connection = Mock(), Mock()
        process.is_alive.return_value = True
        connection.poll.return_value = False
        probe.process, probe.connection = process, connection
        self.assertIsNone(probe.snapshot())
        process.terminate.assert_called_once()
        process.join.assert_called_once()
        self.assertIsNone(probe.process)

    def test_successful_reply_restores_immutable_target_id(self):
        probe = FocusProbe()
        probe.start = Mock()
        probe.ready = True
        connection = Mock()
        connection.poll.return_value = True
        connection.recv.return_value = dict(hwnd=1,pid=2,process='editor.exe',runtime_id=[1,2],
                                           automation_id='text',name='Editor',password=False,editable=True)
        probe.connection = connection
        self.assertEqual(probe.snapshot().runtime_id, (1,2))
