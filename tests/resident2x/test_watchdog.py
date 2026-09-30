import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime,timezone
from scripts import resident2x_watchdog as watchdog
from runtime.resident2x.executor import singleton


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=self.root/'config.json'
        self.config.write_text(json.dumps({'identity':'RESIDENT_ADA_2X_HOME01','instance_id':'test',
            'control_plane':'POSTGRESQL','work_sources':['POSTGRESQL'],
            'capabilities':{'ecos.2x.execute':1},'state_directory':str(self.root)}))
        (self.root/'installed-manifest.json').write_text(json.dumps({'files':{}}))
        self.root_patch=patch.object(watchdog,'ROOT',self.root);self.root_patch.start();self.addCleanup(self.root_patch.stop)
        self.args=patch('sys.argv',['watchdog','--config',str(self.config.resolve())]);self.args.start();self.addCleanup(self.args.stop)

    def test_live_locked_resident_is_not_duplicated(self):
        (self.root/'heartbeat.json').write_text(json.dumps({'instance_id':'test','at':datetime.now(timezone.utc).isoformat()}))
        with singleton(self.root/'resident2x.lock'), patch.object(watchdog.subprocess,'run') as run:
            self.assertEqual(watchdog.main(),0)
            run.assert_not_called()

    def test_dead_or_unhealthy_lock_never_launches_duplicate(self):
        (self.root/'heartbeat.json').write_text(json.dumps({'instance_id':'test','at':'2020-01-01T00:00:00Z'}))
        with singleton(self.root/'resident2x.lock'), patch.object(watchdog.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):watchdog.main()
            run.assert_not_called()

    def test_unlocked_runtime_launches_exact_config_and_returns_exit_code(self):
        with patch.object(watchdog.subprocess,'run',return_value=Mock(returncode=7)) as run:
            self.assertEqual(watchdog.main(),7)
            self.assertEqual(run.call_args.args[0][-2:],['--config',str(self.config.resolve())])

    def test_manifest_tampering_blocks_launch(self):
        (self.root/'payload').write_text('changed')
        (self.root/'installed-manifest.json').write_text(json.dumps({'files':{'payload':'0'*64}}))
        with patch.object(watchdog.subprocess,'run') as run:
            with self.assertRaises(ValueError):watchdog.main()
            run.assert_not_called()
