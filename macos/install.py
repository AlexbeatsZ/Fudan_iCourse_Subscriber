"""Install task-owned user LaunchAgents; no runtime/PATH/system changes."""
import os
import plistlib
from pathlib import Path
import subprocess
from macos.sync import BASE, RUNTIME
from macos.build import build


def install():
    build()
    agents=Path.home()/'Library'/'LaunchAgents'
    agents.mkdir(parents=True,exist_ok=True)
    RUNTIME.mkdir(parents=True,exist_ok=True)
    python=str(BASE/'.venv'/'bin'/'python')
    for name,args in [('player',['-m','macos.app']),('videos',['-m','macos.sync','videos','--watch']),('elearning',['-m','macos.sync','elearning','--watch'])]:
        label='com.meta.icourse.'+name
        path=agents/(label+'.plist')
        cfg={'Label':label,'ProgramArguments':[python,*args],'WorkingDirectory':str(BASE), 'RunAtLoad':True,'KeepAlive':True,
             'ProcessType':'Background' if name!='player' else 'Interactive', 'ThrottleInterval':15,
             'StandardOutPath':str(RUNTIME/(name+'.log')),'StandardErrorPath':str(RUNTIME/(name+'-error.log'))}
        if path.exists():
            old=plistlib.loads(path.read_bytes())
            if old.get('WorkingDirectory')!=str(BASE):
                raise RuntimeError('Existing unrelated LaunchAgent: '+label)
            subprocess.run(['/bin/launchctl','bootout','gui/'+str(os.getuid()),str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        path.write_bytes(plistlib.dumps(cfg))
        subprocess.run(['/bin/launchctl','bootstrap','gui/'+str(os.getuid()),str(path)],check=True)
    (BASE/'macos'/'启动播放器.command').chmod(0o755)
    print('Installed player and independent video/material workers.')


if __name__=='__main__':
    install()
