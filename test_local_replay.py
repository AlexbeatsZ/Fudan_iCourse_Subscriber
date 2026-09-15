import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from local_replay import timeline, write_player, download_video, course_id, fetch_ppt, make_server


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


class ImageResponse:
    status_code=200
    content=b'jpeg'
    headers={"Content-Type":"image/jpeg"}
    def raise_for_status(self):pass


class ImageVPN:
    def __init__(self):self.called=[]
    def get(self,url,**kw):self.called.append(('get',url));return ImageResponse()
    def get_raw(self,url,**kw):self.called.append(('get_raw',url));return ImageResponse()


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

    def test_corrupt_partial_is_quarantined_before_restart(self):
        body=b'\x00\x00\x00\x18ftypisom'+b'x'*30
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'video.mp4'
            p.with_suffix('.mp4.part').write_bytes(b'old-part')
            p.with_suffix('.mp4.json').write_bytes(b'\x00'*20)
            download_video(Client(Response(body,0,len(body))),'https://example.com/v.mp4',p)
            self.assertEqual(p.read_bytes(),body)
            quarantined=list(Path(d).glob('video.mp4.part.invalid-*'))
            self.assertEqual(len(quarantined),1)
            self.assertEqual(quarantined[0].read_bytes(),b'old-part')

    def test_course_url_host(self):
        self.assertEqual(course_id('https://icourse.fudan.edu.cn/coursedetail?course_id=37113'),'37113')
        with self.assertRaises(ValueError):course_id('https://example.com/?course_id=37113')

    def test_ppt_webvpn_url_is_not_encoded_twice(self):
        vpn=ImageVPN()
        self.assertEqual(fetch_ppt(vpn,'https://webvpn.fudan.edu.cn/encoded.jpg'),b'jpeg')
        self.assertEqual(fetch_ppt(vpn,'https://icourse.fudan.edu.cn/ppt.jpg'),b'jpeg')
        self.assertEqual([name for name,_ in vpn.called],['get_raw','get'])

    def test_local_server_supports_video_ranges(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'video.mp4').write_bytes(b'0123456789')
            server=make_server(Path(d),port=0)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                request=Request(f'http://127.0.0.1:{server.server_port}/video.mp4',headers={'Range':'bytes=3-6'})
                with urlopen(request,timeout=5) as response:
                    self.assertEqual(response.status,206)
                    self.assertEqual(response.headers['Content-Range'],'bytes 3-6/10')
                    self.assertEqual(response.read(),b'3456')
            finally:
                server.shutdown();server.server_close();thread.join(5)


if __name__=='__main__':unittest.main()
