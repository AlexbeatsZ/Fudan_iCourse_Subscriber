"""Open the installed local player after validating its deployment identity."""
import subprocess
import time
from urllib.request import ProxyHandler, build_opener
import json
from macos.sync import RUNTIME, settings


def main():
    url='http://127.0.0.1:'+str(settings()['port'])
    opener=build_opener(ProxyHandler({}))
    for attempt in range(30):
        try:
            with opener.open(url+'/api/health',timeout=1) as response:
                health=json.load(response)
            if health.get('directory')!=str(RUNTIME.resolve()):
                raise RuntimeError('播放器端口已被其他程序使用')
            subprocess.run(['/usr/bin/open',url],check=True)
            return
        except OSError:
            if attempt==0:
                subprocess.run(['/bin/launchctl','kickstart','gui/'+str(__import__('os').getuid())+'/com.meta.icourse.player'],check=True)
            time.sleep(.3)
    raise RuntimeError('播放器暂时无法启动，请查看项目 local-data/mac/player.log')


if __name__=='__main__':
    main()
