import base64
import json
from pathlib import Path
import tempfile
import unittest
from local_replay import timeline, write_player, download_video, course_id


class Response:
    def __init__(self,body,start,total,status=206,validator='"v1"'):
        self.body=body;self.status_code=status
        self.headers={"Content-Range":f"bytes {start}-{total-1}/{total}","ETag":validator}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,n):yield self.body


class Client:
    def __init__(self,response):self.vpn=self;self.response=response;self.headers=None
    def get(self,url,**kw):self.headers=kw.get('headers');return self.response


class ReplayTests(unittest.TestCase):
    def test_timeline_preserves_zero_and_repeated_slide(self):
        pages=timeline([{'id':1,'created_sec':0,'pptimgurl':'a'},
                        {'id':2,'created_sec':20,'pptimgurl':'b'},
                        {'id':3,'created_sec':40,'pptimgurl':'a'},
                        {'id':4,'created_sec':None,'pptimgurl':'c'},
                        {'id':5,'created_sec':-1,'pptimgurl':'d'}])
        self.assertEqual([p['time'] for p in pages],[0,20,40])
        self.assertEqual([p['url'] for p in pages],['a','b','a'])

    def test_download_resume_and_skip(self):
        body=b'\x00\x00\x00\x18ftypisom'+b'x'*30
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'video.mp4';part=p.with_suffix('.mp4.part')
            part.write_bytes(body[:15])
            p.with_suffix('.mp4.json').write_text(json.dumps({'source':'/v.mp4','total':len(body),'validator':'"v1"','complete':False}))
            c=Client(Response(body[15:],15,len(body)))
            download_video(c,'https://example.com/v.mp4',p)
            self.assertEqual(p.read_bytes(),body)
            self.assertEqual(c.headers['Range'],'bytes=15-')
            download_video(Client(None),'https://example.com/v.mp4',p)

    def test_server_ignores_range_preserves_partial(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'video.mp4';part=p.with_suffix('.mp4.part');part.write_bytes(b'old')
            p.with_suffix('.mp4.json').write_text(json.dumps({'source':'/v.mp4','total':100,'validator':'"v1"'}))
            with self.assertRaises(RuntimeError):download_video(Client(Response(b'bad',0,3,200)),'https://example.com/v.mp4',p)
            self.assertEqual(part.read_bytes(),b'old')
            self.assertFalse(p.exists())

    def test_player_escapes_content(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);write_player(p,'<unsafe>',[{'time':0,'file':'</script><script>bad</script>'}])
            text=(p/'index.html').read_text(encoding='utf-8')
            self.assertNotIn('<unsafe>',text)
            self.assertNotIn('</script><script>bad',text)

    def test_corrupt_empty_download_record_can_restart(self):
        body=b'\x00\x00\x00\x18ftypisom'+b'x'*30
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'video.mp4'
            p.with_suffix('.mp4.part').touch()
            p.with_suffix('.mp4.json').write_bytes(b'\x00'*20)
            download_video(Client(Response(body,0,len(body))),'https://example.com/v.mp4',p)
            self.assertEqual(p.read_bytes(),body)
            self.assertEqual(len(list(Path(d).glob('*.invalid-*'))),1)

    def test_course_url_host(self):
        self.assertEqual(course_id('https://icourse.fudan.edu.cn/coursedetail?course_id=37113'),'37113')
        with self.assertRaises(ValueError):course_id('https://example.com/?course_id=37113')


if __name__=='__main__':unittest.main()
