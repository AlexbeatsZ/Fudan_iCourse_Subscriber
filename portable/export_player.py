"""Export the existing UI and standalone server to a portable Windows directory."""
import argparse
import json
from pathlib import Path
import shutil
from urllib.request import urlopen
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent
RUNTIME_VERSION = "3.13.16"
RUNTIME_URL = f"https://www.python.org/ftp/python/{RUNTIME_VERSION}/python-{RUNTIME_VERSION}-embed-amd64.zip"


def player_html(source):
    lines = source.splitlines()
    replaced = set()
    for index, line in enumerate(lines):
        if line.startswith("<header>"):
            lines[index] = '<header><div class="brand"><span class="mark" aria-hidden="true"></span><strong>课程库</strong></div><nav><button id="refresh">刷新课程</button><button id="settings">设置</button></nav></header>'
            replaced.add("header")
        elif line.startswith('<dialog id="dialog">'):
            lines[index] = '<dialog id="dialog"><form id="form"><h2>播放器设置</h2><label>视频目录<input name="destination" required></label><div class="actions"><button type="button" id="cancel">取消</button><button class="primary">保存</button></div></form></dialog>'
            replaced.add("dialog")
        elif line.startswith("async function refresh("):
            lines[index] = "async function refresh(show=true){try{const r=await fetch('/api/library');if(!r.ok)throw Error();state=await r.json();if(show)showLibrary();$('notice').textContent=state.courses.length?'':'视频目录暂无课程录像。请在设置中检查目录。'}catch{$('notice').textContent='暂时无法连接播放器，请重新打开。'}}"
            replaced.add("refresh")
        elif line.startswith("async function post("):
            lines[index] = "async function post(url,data){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-Course-Token':state.token},body:JSON.stringify(data)});const v=await r.json();if(!r.ok)throw Error(v.error);return v}$('refresh').onclick=()=>refresh($('player').classList.contains('hidden')&&!course);$('settings').onclick=()=>{$('form').elements.destination.value=state.settings.destination;$('dialog').showModal()};$('cancel').onclick=()=>$('dialog').close();$('form').onsubmit=async e=>{e.preventDefault();try{await post('/api/settings',Object.fromEntries(new FormData(e.target)));$('dialog').close();await refresh($('player').classList.contains('hidden'))}catch(err){$('notice').textContent=err.message;$('dialog').close()}};refresh();setInterval(()=>refresh($('player').classList.contains('hidden')&&!course),15000);"
            replaced.add("actions")
    if replaced != {"header", "dialog", "refresh", "actions"}:
        raise ValueError("Player UI changed; review the portable export transformations")
    output = "\n".join(lines) + "\n"
    output = output.replace("还没有课程录像。在“管理课程”中检查并下载。", "还没有课程录像。请在设置中选择已有的视频目录。")
    output = output.replace("字幕生成后，点击“同步字幕”即可补齐。", "本节暂无字幕。字幕文件到达后，重新打开本节即可显示。")
    return output


def export(destination, archive):
    destination = destination.resolve()
    if (destination / "settings.json").exists():
        raise FileExistsError("An existing player deployment was found; preserve its settings before updating")
    (destination / "app").mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "player.py", destination / "app" / "player.py")
    (destination / "app" / "index.html").write_text(
        player_html((HERE.parent / "desktop" / "index.html").read_text(encoding="utf-8-sig")), encoding="utf-8")
    for name in ("start-player.ps1", "README.md", "AGENTS.md"):
        shutil.copy2(HERE / name, destination / name)
    shutil.copy2(HERE / "start-player.vbs", destination / "启动播放器.vbs")
    shutil.copy2(HERE / "stop-player.vbs", destination / "停止播放器.vbs")
    (destination / "settings.json").write_text(
        json.dumps({"destination": r"D:\Videos", "port": 8765}, indent=2) + "\n", encoding="utf-8")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print(f"Downloading embedded Python {RUNTIME_VERSION}...", flush=True)
        with urlopen(RUNTIME_URL, timeout=60) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    with ZipFile(archive) as package:
        package.extractall(destination / "runtime")
    (destination / "deployment.json").write_text(
        json.dumps({"application": "icourse-portable-player", "version": "1.0.0",
                    "runtime": RUNTIME_VERSION, "runtime_source": RUNTIME_URL}, indent=2) + "\n", encoding="utf-8")
    print(f"Deployed: {destination}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--runtime-archive", type=Path, required=True)
    args = parser.parse_args()
    export(args.destination, args.runtime_archive)
