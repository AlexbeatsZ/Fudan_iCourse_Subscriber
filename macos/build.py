"""Build the Mac view from the shared portable player; no global dependencies."""
from pathlib import Path
from portable.export_player import player_html
from macos.sync import BASE, RUNTIME, DEFAULT, write_json

SCRIPT = r'''
<script>
const humanBytes=n=>{if(!n)return '0 B';const i=Math.min(3,Math.floor(Math.log(n)/Math.log(1024)));return (n/1024**i).toFixed(i?1:0)+' '+['B','KB','MB','GB'][i]};
async function syncStatus(){try{const response=await fetch('/api/sync');const data=await response.json();for(const kind of ['videos','elearning']){const s=data[kind],box=document.getElementById('sync-'+kind);const message=(s.paused?'已暂停':s.message||'等待同步')+(s.network?' · '+s.network:'');box.querySelector('.sync-message').textContent=message;box.querySelector('.sync-file').textContent=s.phase==='transferring'?(s.file+' · '+humanBytes(s.file_bytes)+' / '+humanBytes(s.file_size)):(s.pending_files?'待同步 '+s.pending_files+' 个文件 · '+humanBytes(s.pending_bytes):s.last_success?'上次成功 '+new Date(s.last_success*1000).toLocaleString():'');const btn=box.querySelector('.sync-pause');btn.textContent=s.paused?'继续':'暂停';btn.onclick=()=>syncAction(kind,s.paused?'resume':'pause');box.querySelector('.sync-retry').onclick=()=>syncAction(kind,'retry')}}catch{}}
async function syncAction(kind,action){try{if(!state)await refresh(false);await post('/api/sync',{kind,action});await syncStatus()}catch(e){$('notice').textContent=e.message}}
async function showMaterials(path=''){const r=await fetch('/api/materials?path='+encodeURIComponent(path));const data=await r.json();const list=$('materials-list');list.replaceChildren();$('materials-heading').textContent=path||'Elearning 课程资料';if(path){const back=el('button','← 上一级','back');back.onclick=()=>showMaterials(path.split('/').slice(0,-1).join('/'));list.append(back)}if(!r.ok){list.append(el('p',data.error,'muted'));return}for(const item of data.files){const row=el('div',undefined,'material-row');if(item.directory){const b=el('button',item.name+' →');b.onclick=()=>showMaterials(item.path);row.append(b)}else{const link=el('a',item.name);link.href='/materials/'+item.path.split('/').map(encodeURIComponent).join('/');link.target='_blank';link.rel='noopener';row.append(link,el('span',humanBytes(item.size),'muted'));if(/\.(pdf|pptx?|docx?|xlsx?|txt|png|jpe?g)$/i.test(item.name)){const open=el('button','在本机打开');open.onclick=async()=>{try{await post('/api/materials/open',{path:item.path})}catch(e){$('notice').textContent=e.message}};row.append(open)}}list.append(row)}if(!data.files.length)list.append(el('p','本目录暂无已归档文件。','muted'))}
$('materials-button').onclick=()=>{showMaterials();$('materials-dialog').showModal()};$('materials-close').onclick=()=>$('materials-dialog').close();syncStatus();setInterval(syncStatus,3000);
</script>
'''


def build():
    app = RUNTIME / 'app'
    app.mkdir(parents=True, exist_ok=True)
    html = player_html((BASE / 'desktop' / 'index.html').read_text(encoding='utf-8-sig'))
    html = html.replace('<button id="refresh">', '<button id="materials-button">课程资料</button><button id="refresh">', 1)
    panel = '<details class="sync-panel"><summary>资料同步状态</summary>' + ''.join(
        '<div id="sync-'+kind+'" class="sync-row"><strong>'+title+'</strong><span class="sync-message"></span><button class="sync-retry">立即同步</button><button class="sync-pause">暂停</button><small class="sync-file"></small></div>'
        for kind,title in [('videos','iCourse 视频'),('elearning','Elearning 资料')]) + '</details>'
    html = html.replace('<main>', '<main>'+panel, 1)
    extra = '<style>.sync-panel{padding:16px 0;border-bottom:1px solid var(--line);font-size:13px;color:var(--muted)}.sync-row{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:12px 0}.sync-row strong{color:var(--ink);min-width:110px}.sync-file{width:100%;overflow-wrap:anywhere}.material-row{display:flex;gap:16px;align-items:center;border-bottom:1px solid var(--line);padding:12px 0}.material-row a{color:var(--ink);flex:1;overflow-wrap:anywhere}#materials-dialog{width:min(1000px,94vw);max-height:85vh;overflow:auto}</style>'
    modal='<dialog id="materials-dialog"><div class="actions"><button id="materials-close">关闭</button></div><h2 id="materials-heading"></h2><div id="materials-list"></div></dialog>'
    html=html.replace('</body>',modal+extra+SCRIPT+'</body>')
    (app/'index.html').write_text(html,encoding='utf-8')
    if not (RUNTIME/'settings.json').exists():
        write_json(RUNTIME/'settings.json', DEFAULT)
    print('Built Mac player:',app/'index.html')


if __name__=='__main__':
    build()
