"""Acceptance of network separation, interrupted copies and local API boundaries."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import build_opener, ProxyHandler, Request
from urllib.error import HTTPError

from macos import sync, manifest, app
from portable.player import make_app


class MacSyncTests(unittest.TestCase):
    def setUp(self):
        Path('/tmp/.agents').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir='/tmp/.agents',prefix='mac-sync-test-')
        self.base=Path(self.temp.name)
        self.runtime=self.base/'runtime'
        self.destination=self.base/'videos'
        self.materials=self.base/'materials'
        self.materials.mkdir()
        self.runtime.mkdir()
        sync.write_json(self.runtime/'settings.json',{'destination':str(self.destination),'materials':str(self.materials),'port':8765})
        self.overrides=patch.multiple(sync,RUNTIME=self.runtime)
        self.overrides.start()

    def tearDown(self):
        self.overrides.stop()
        self.temp.cleanup()

    def test_video_cannot_use_remote_even_when_requested_by_ui(self):
        with patch.object(sync,'lan_interface',return_value=None):
            with self.assertRaises(sync.Waiting): sync.connection('videos')
            self.assertEqual(sync.connection('elearning'),(sync.REMOTE,None))
            with patch.object(sync,'manifest') as remote:
                sync.control('videos','retry')
                sync.sync_once('videos')
                remote.assert_not_called()
        status=sync.read_json(self.runtime/'videos-status.json',{})
        self.assertEqual(status['phase'],'waiting')
        with self.assertRaises(sync.Waiting):
            sync.transfer_file('videos',sync.REMOTE,'en0','D:/Videos/Icouse',{'path':'x.mp4'},self.base/'x.part',lambda:None)

    def test_command_is_terminated_when_lan_route_disappears(self):
        import sys
        with patch.object(sync,'lan_interface',side_effect=['en0',None]):
            with self.assertRaises(sync.Waiting):
                sync.guarded_command([sys.executable,'-c','import time; time.sleep(30)'],'','videos','en0')

    def test_batch_path_cannot_inject_commands(self):
        with self.assertRaises(ValueError): sync.sftp_quote('file\nput secrets remote')

    def test_route_rejects_vpn_gateway_and_other_subnet(self):
        def command(argv,**kwargs):
            class Result: returncode=0
            r=Result()
            r.stdout=' interface: en0\n flags: <UP,HOST,GATEWAY>\n' if 'route' in argv[0] else 'inet 192.168.31.10 netmask 0xffffff00'
            return r
        with patch.object(sync.subprocess,'run',side_effect=command): self.assertIsNone(sync.lan_interface())
        with patch.object(sync.subprocess,'run',return_value=type('R',(),{'returncode':0,'stdout':' interface: utun4\n flags: <UP,HOST>\n'})()): self.assertIsNone(sync.lan_interface())

    def test_resume_preserves_previous_file_and_source_deletions(self):
        target=self.destination/'Course'/'第01节.mp4'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'local edit')
        row={'path':'Course/第01节.mp4','size':10,'mtime_ns':1000000000}
        listing={'root':'D:/Videos/Icouse','files':[row]}
        offsets=[]
        def interrupted(kind,host,interface,remote_root,value,partial,tick):
            partial.write_bytes(b'01234')
            raise sync.Waiting('断线')
        with patch.object(sync,'connection',return_value=(sync.LAN,'en0')),patch.object(sync,'manifest',return_value=listing),patch.object(sync,'transfer_file',side_effect=interrupted):
            sync.sync_once('videos')
        self.assertEqual(target.read_bytes(),b'local edit')
        def resumed(kind,host,interface,remote_root,value,partial,tick):
            offsets.append(partial.stat().st_size)
            with partial.open('ab') as stream: stream.write(b'56789')
        def source(kind,host,interface,path=None): return row if path else listing
        with patch.object(sync,'connection',return_value=(sync.LAN,'en0')),patch.object(sync,'manifest',side_effect=source),patch.object(sync,'transfer_file',side_effect=resumed):
            sync.sync_once('videos')
            sync.sync_once('videos')
        self.assertEqual(offsets,[5])
        self.assertEqual(target.read_bytes(),b'0123456789')
        history=list((self.destination/'.icourse-sync'/'history').rglob('*.mp4'))
        self.assertEqual(history[0].read_bytes(),b'local edit')
        with patch.object(sync,'connection',return_value=(sync.LAN,'en0')),patch.object(sync,'manifest',return_value={'root':'D:/Videos/Icouse','files':[]}): sync.sync_once('videos')
        self.assertTrue(target.exists())

    def test_changed_source_discards_old_partial(self):
        row={'path':'Course/a.mp4','size':4,'mtime_ns':2}
        key=sync.hashlib.sha256(row['path'].encode()).hexdigest()[:32]
        work=self.destination/'.icourse-sync'/'partial'
        work.mkdir(parents=True)
        (work/(key+'.part')).write_bytes(b'old')
        sync.write_json(work/(key+'.json'),{**row,'mtime_ns':1})
        def copy(*args):
            partial=args[5]
            self.assertFalse(partial.exists())
            partial.write_bytes(b'new!')
        def source(kind,host,interface,path=None): return row if path else {'root':'D:/Videos/Icouse','files':[row]}
        with patch.object(sync,'connection',return_value=(sync.LAN,'en0')),patch.object(sync,'manifest',side_effect=source),patch.object(sync,'transfer_file',side_effect=copy): sync.sync_once('videos')
        self.assertEqual((self.destination/row['path']).read_bytes(),b'new!')

    def test_changed_sidecar_does_not_block_other_files(self):
        rows=[{'path':'Course/a.json','size':4,'mtime_ns':1},{'path':'Course/b.mp4','size':4,'mtime_ns':1}]
        def copy(*args): args[5].write_bytes(b'data')
        def source(kind,host,interface,path=None):
            if not path: return {'root':'D:/Videos/Icouse','files':rows}
            return {**rows[0],'mtime_ns':2} if path.endswith('a.json') else rows[1]
        with patch.object(sync,'connection',return_value=(sync.LAN,'en0')),patch.object(sync,'manifest',side_effect=source),patch.object(sync,'transfer_file',side_effect=copy): sync.sync_once('videos')
        self.assertFalse((self.destination/'Course/a.json').exists())
        self.assertEqual((self.destination/'Course/b.mp4').read_bytes(),b'data')

    def test_manifest_excludes_unfinished_and_unrelated_courses(self):
        course=self.base/'source'/'Course'
        course.mkdir(parents=True)
        (course/'course.json').write_text('{"course_id":"1"}')
        (course/'第01节.mp4').write_bytes(b'done')
        (course/'第01节.mp4.json').write_text('{"complete":true,"total":4}')
        (course/'第02节.mp4').write_bytes(b'partial')
        (course/'第02节.mp4.json').write_text('{"complete":false,"total":30}')
        (course/'第01节.vtt.tmp').write_text('unfinished')
        unrelated=course.parent/'Unrelated'; unrelated.mkdir(); (unrelated/'film.mp4').write_bytes(b'film')
        rows=manifest.collect('videos',course.parent)
        self.assertEqual([r['path'] for r in rows],['Course/course.json','Course/第01节.mp4.json','Course/第01节.mp4'])

    def test_material_api_host_token_and_path_boundaries(self):
        (self.runtime/'app').mkdir()
        (self.runtime/'app'/'index.html').write_text('Player')
        (self.materials/'x.pdf').write_bytes(b'PDF')
        with patch.object(app,'RUNTIME',self.runtime):
            server=make_app(self.runtime,port=0,extension=app.Extension())
            thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
            opener=build_opener(ProxyHandler({})); url='http://127.0.0.1:'+str(server.server_port)
            try:
                with opener.open(url+'/api/materials') as response: self.assertEqual(json.load(response)['files'][0]['name'],'x.pdf')
                for path in ['/materials/../settings.json','/materials/%2e%2e/settings.json','/materials/.secret']:
                    with self.assertRaises(HTTPError) as error: opener.open(url+path)
                    self.assertEqual(error.exception.code,404); error.exception.close()
                with self.assertRaises(HTTPError) as error: opener.open(Request(url+'/api/sync',data=b'{"kind":"videos","action":"retry"}',headers={'Content-Type':'application/json'}))
                self.assertEqual(error.exception.code,403); error.exception.close()
                with opener.open(url+'/api/library') as response: token=json.load(response)['token']
                with opener.open(Request(url+'/api/sync',data=b'{"kind":"videos","action":"pause"}',headers={'Content-Type':'application/json','X-Course-Token':token})) as response: self.assertTrue(json.load(response)['ok'])
                self.assertTrue(sync.controls('videos')['paused'])
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__=='__main__': unittest.main()
