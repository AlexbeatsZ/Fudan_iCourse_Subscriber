"""Local video + synchronized PPT export, using the upstream API client.

Run with: uv run --with requests --with pycryptodome local_replay.py --help
"""
import argparse
import getpass
import html
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlparse, parse_qs


def write_json(path, value):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w',encoding='utf-8') as out:
        json.dump(value,out,ensure_ascii=False,indent=2)
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)


def course_id(value):
    if value.isdigit():
        return value
    url = urlparse(value)
    result = parse_qs(url.query).get("course_id", [""])[0]
    if url.hostname != "icourse.fudan.edu.cn" or not result.isdigit():
        raise ValueError("请输入课程编号或 iCourse 课程目录链接")
    return result


def timeline(items):
    """Preserve every occurrence, including repeated images and time zero."""
    result = []
    for order,item in enumerate(items):
        raw = item.get("created_sec")
        try:
            seconds = float(raw)
        except (ValueError,TypeError):
            continue
        if not math.isfinite(seconds) or seconds < 0:
            continue
        result.append({"time":seconds,"id":str(item.get("id",order)),
                       "url":item["pptimgurl"],"order":order})
    return sorted(result,key=lambda x:(x["time"],x["order"]))


def write_player(folder,title,pages):
    payload = json.dumps(pages,ensure_ascii=False).replace("<","\\u003c")
    template = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>body{margin:0;background:#16191d;color:#eee;font:16px system-ui}header{padding:18px 24px}main{display:grid;grid-template-columns:3fr 2fr;gap:16px;padding:0 24px}video{width:100%;background:black}#slide{width:100%;object-fit:contain;max-height:65vh}nav{display:flex;gap:8px;overflow:auto;padding:20px 24px}button{background:#262d37;color:white;border:2px solid transparent;padding:8px;cursor:pointer;min-width:120px}button img{width:120px;display:block}button[aria-current=true]{border-color:#65abff}small{display:block;color:#b7c4d8;padding:0 24px 16px}@media(max-width:800px){main{grid-template-columns:1fr}}</style>
<header>__TITLE__</header><main><video id="video" controls preload="metadata" src="video.mp4"></video><section><img id="slide" alt="对应 PPT"><p id="caption"></p></section></main>
<nav id="pages"></nav><small id="status">点击 PPT 跳转；播放时自动切换。时间来自平台记录。</small>
<script>const data=__DATA__;const video=document.getElementById('video'),slide=document.getElementById('slide'),caption=document.getElementById('caption'),nav=document.getElementById('pages');let active=-1;
function stamp(t){return Math.floor(t/60)+':'+String(Math.floor(t%60)).padStart(2,'0')}
function select(i){if(i===active)return;active=i;nav.querySelectorAll('button').forEach((b,j)=>b.setAttribute('aria-current',String(i===j)));if(i<0){slide.removeAttribute('src');caption.textContent='此时间尚无 PPT';return}slide.src=data[i].file;caption.textContent='第 '+(i+1)+' 个画面 · '+stamp(data[i].time)}
data.forEach((p,i)=>{const b=document.createElement('button'),img=document.createElement('img');img.src=p.file;img.loading='lazy';img.alt='PPT '+(i+1);b.append(img,document.createTextNode(stamp(p.time)));b.onclick=()=>{if(!Number.isFinite(video.duration)){document.getElementById('status').textContent='请先加载本地视频';return}if(p.time>video.duration){document.getElementById('status').textContent='此页时间超过视频长度';return}video.currentTime=p.time;select(i)};nav.append(b)});
video.addEventListener('timeupdate',()=>{let i=-1;for(let j=0;j<data.length&&data[j].time<=video.currentTime;j++)i=j;select(i)});
video.addEventListener('loadedmetadata',()=>{const n=data.filter(p=>p.time>video.duration).length;if(n)document.getElementById('status').textContent=n+' 个 PPT 时间超过视频长度，请检查录制版本。'});
if(!data.length)document.getElementById('status').textContent='本课次没有可用 PPT 时间索引';
</script></html>"""
    (folder / "index.html").write_text(template.replace("__TITLE__",html.escape(title)).replace("__DATA__",payload),encoding="utf-8")


def download_video(client,url,path):
    """Resume only when server supplies a stable validator and exact ranges."""
    part=path.with_suffix(".mp4.part")
    record=path.with_suffix(".mp4.json")
    identity=urlparse(url).path
    try:
        meta=json.loads(record.read_text()) if record.exists() else {}
    except (ValueError,UnicodeError):
        if path.exists() or (part.exists() and part.stat().st_size):
            raise RuntimeError("下载记录损坏，保留原文件；请更换输出目录") from None
        record.replace(record.with_name(record.name+f'.invalid-{time.time_ns()}'))
        meta={}
    if path.exists():
        if meta.get("complete") and meta.get("source")==identity and path.stat().st_size==meta.get("total"):
            return
        raise RuntimeError("已有视频缺少匹配完成记录；未覆盖")
    start=part.stat().st_size if part.exists() else 0
    if start and meta.get("source")==identity and start==meta.get("total"):
        part.replace(path);meta["complete"]=True
        write_json(record,meta)
        return
    if start and (meta.get("source")!=identity or not meta.get("validator") or start>meta.get("total",0)):
        raise RuntimeError("无法验证原片段来源；未覆盖")
    headers={"Range":f"bytes={start}-","Accept-Encoding":"identity"}
    if start:
        headers["If-Range"]=meta["validator"]
    with client.vpn.get(url,headers=headers,stream=True,timeout=120) as response:
        if response.status_code!=206:
            raise RuntimeError(f"视频未返回可续传内容 (HTTP {response.status_code})")
        match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",response.headers.get("Content-Range",""))
        if not match or int(match[1])!=start or int(match[2])!=int(match[3])-1:
            raise RuntimeError("视频字节范围异常")
        total=int(match[3]);validator=response.headers.get("ETag") or response.headers.get("Last-Modified")
        if start and (total!=meta.get("total") or validator!=meta.get("validator")):
            raise RuntimeError("视频版本已变化，停止续传")
        meta={"source":identity,"total":total,"validator":validator,"complete":False}
        write_json(record,meta)
        last_report=0
        with part.open("ab") as out:
            for chunk in response.iter_content(1024*1024):
                if not chunk:continue
                if start==0 and chunk[4:8] not in (b"ftyp",b"moov",b"mdat",b"free",b"wide"):
                    raise RuntimeError("响应不是 MP4")
                out.write(chunk);start+=len(chunk)
                if time.monotonic()-last_report>=10 or start==total:
                    out.flush()
                    os.fsync(out.fileno())
                    print(f"{start/1048576:.0f} / {total/1048576:.0f} MiB",flush=True)
                    last_report=time.monotonic()
        if start!=total:raise RuntimeError("下载不完整，重新运行可续传")
    part.replace(path);meta["complete"]=True
    write_json(record,meta);print()


def main():
    p=argparse.ArgumentParser(description="保存课程，下载视频与 PPT，生成离线联动播放器")
    p.add_argument("command",choices=["add","list","download"])
    p.add_argument("course",nargs="?",help="课程编号或目录链接")
    p.add_argument("--lesson",help="仅下载指定课次")
    p.add_argument("--proxy",help="可选 HTTP/SOCKS 代理；默认直连 WebVPN，不继承系统环境代理")
    p.add_argument("--root",type=Path,default=Path(__file__).resolve().parent/"local-data")
    args=p.parse_args();args.root.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(args.root/"library.sqlite3")
    db.execute("CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY,title TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS downloads(course TEXT,lesson TEXT,status TEXT,folder TEXT,PRIMARY KEY(course,lesson))")
    try:
        if args.command=="list":
            for row in db.execute("SELECT id,title FROM courses ORDER BY title"):print(*row)
            return
        if not args.course:raise ValueError("需要课程编号或目录链接")
        cid=course_id(args.course)
        from src.api.webvpn import WebVPNSession
        from src.api.icourse import ICourseClient
        account=os.environ.get("StuId") or input("学号：")
        password=os.environ.get("UISPsw") or getpass.getpass("统一身份认证密码：")
        vpn=None
        for attempt in range(3):
            try:
                vpn=WebVPNSession()
                vpn.session.trust_env=False
                if args.proxy:
                    vpn.session.proxies.update({'http':args.proxy,'https':args.proxy})
                vpn.login(account,password);vpn.authenticate_icourse(account,password)
                if not ICourseClient(vpn).check_alive():
                    raise RuntimeError("登录会话验证失败")
                break
            except Exception:
                if vpn: vpn.session.close()
                if attempt==2:raise
                print("登录链路暂时失败，重新建立会话…",flush=True)
                time.sleep(3)
        password=None
        client=ICourseClient(vpn);detail=client.get_course_detail(cid)
        with db:db.execute("INSERT INTO courses VALUES(?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title",(cid,detail["title"]))
        print(f"{detail['title']}：{len(detail['lectures'])} 节")
        if args.command=="add":return
        ready=[l for l in detail["lectures"] if l["has_playback"] and (not args.lesson or str(l["sub_id"])==args.lesson)]
        if not ready:raise RuntimeError("没有匹配的已就绪回放")
        for lecture in ready:
            sid=str(lecture["sub_id"])
            if not sid.isdigit():raise ValueError("无效课次编号")
            folder=args.root/cid/sid;folder.mkdir(parents=True,exist_ok=True)
            with db:db.execute("INSERT INTO downloads VALUES(?,?,?,?) ON CONFLICT(course,lesson) DO UPDATE SET status=excluded.status",(cid,sid,"downloading",str(folder)))
            # Require successful access before invoking upstream URL fallbacks.
            check=vpn.get(client.base_url+"/courseapi/v3/portal-home-setting/get-sub-info",params={"course_id":cid,"sub_id":sid},timeout=30)
            check.raise_for_status()
            if check.json().get("code")!=0:raise RuntimeError("该课次尚未开放或没有访问权限")
            url=client.get_video_url(cid,sid)
            if not url:raise RuntimeError("没有可下载的视频")
            pages=timeline(client.get_ppt_list(cid,sid));(folder/"ppt").mkdir(exist_ok=True)
            for i,item in enumerate(pages):
                target=folder/"ppt"/f"{i+1:05}.jpg"
                if not target.exists():
                    response=vpn.get(item["url"],timeout=60);response.raise_for_status()
                    if not response.headers.get("Content-Type","").startswith("image/"):raise RuntimeError("PPT 响应不是图片")
                    temp=target.with_suffix(".part");temp.write_bytes(response.content);temp.replace(target)
                item["file"]=f"ppt/{target.name}";item.pop("url",None)
            (folder/"timeline.json").write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding="utf-8")
            write_player(folder,detail["title"]+" "+lecture["sub_title"],pages)
            print(f"已保存 {len(pages)} 个 PPT 时间事件，开始下载视频。",flush=True)
            # Refresh the expiring URL after fetching all slide images.
            url=client.get_video_url(cid,sid)
            if not url:raise RuntimeError("视频地址刷新失败")
            download_video(client,url,folder/"video.mp4")
            with db:db.execute("UPDATE downloads SET status='complete' WHERE course=? AND lesson=?",(cid,sid))
            print(f"打开：{folder/'index.html'}")
    except BaseException:
        if 'cid' in locals() and 'sid' in locals():
            with db:db.execute("UPDATE downloads SET status='incomplete' WHERE course=? AND lesson=?",(cid,sid))
        raise
    finally:
        if 'vpn' in locals() and vpn: vpn.session.close()
        db.close()


if __name__=="__main__":
    try:main()
    except KeyboardInterrupt:print("已停止，片段保留。")
    except Exception as error:
        # Never echo request exceptions which can include signed URLs.
        print(f"未完成 ({type(error).__name__})，请检查登录、网络及课程权限。")
        raise SystemExit(1)
