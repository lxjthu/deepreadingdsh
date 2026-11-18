"""Read-only acceptance of the installed local host; no sample imports or model calls."""
import json
import os
import re
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(r'D:\code\deepseek-harness-runtime')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',r'C:\Users\langx\AppData\Local\ms-playwright')

def run():
    installed=RUNTIME/'data/profiles/web/node_modules/dsh-deep-reading'
    names=['scripts/server.py','scripts/research_wiki.py','web/app.js','web/wiki.js',
           'web/index.html','web/style.css','panel-proxy.js','package.json']
    for name in names:assert (ROOT/name).read_bytes()==(installed/name).read_bytes(),name
    version=json.loads((installed/'package.json').read_text(encoding='utf-8'))['version']
    connection=json.loads((RUNTIME/'data/deep-reading/connection.json').read_text(encoding='utf-8-sig'))
    state=json.load(urllib.request.urlopen(urllib.request.Request(connection['url']+'/api/state',headers={'X-Reading-Token':connection['token']}),timeout=5))
    text=(RUNTIME/'logs/server.out.log').read_text(encoding='utf-8')
    private_url=re.findall(r'dsh web: (https?://\S+)',text)[-1]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':1500,'height':1100});errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)));page.goto(private_url)
            page.get_by_role('button',name='文献研究',exact=True).click(timeout=20000)
            frame=page.frame_locator('iframe');expect(frame.locator('#papers')).to_be_visible(timeout=25000)
            frame.get_by_role('button',name='研究 Wiki',exact=True).click()
            expect(frame.locator('#wiki-count')).to_contain_text('个实体')
            expect(frame.locator('#wiki-kind option')).to_have_count(8)
            expect(frame.locator('#wiki-extract')).to_be_visible()
            asset=frame.locator('body').evaluate("async()=>{const r=await fetch(new URL('./wiki.js',document.baseURI));return {status:r.status,hasEditor:(await r.text()).includes('wikiEditor')}}")
            assert asset=={'status':200,'hasEditor':True},asset
            page.screenshot(path=str(ROOT/'verification/wiki-host-installed.png'),full_page=True)
            page.set_viewport_size({'width':800,'height':1000});expect(frame.locator('#wiki-extract')).to_be_visible()
            page.screenshot(path=str(ROOT/'verification/wiki-host-narrow.png'),full_page=True)
            assert not errors,errors
            report={'version':version,'matched_installed_files':names,'host_sidebar':True,'installed_panel':True,
                    'wiki_entry':True,'seven_type_options':True,'proxy_asset':asset,'page_errors':errors,
                    'formal_topics':len(state['topics']),'formal_documents':len(state['documents']),
                    'active_tasks':sum(t['status'] in ('running','queued') for t in state['tasks']),'live_model_used':False}
            (ROOT/'verification/wiki-host-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False))
        finally:browser.close()

if __name__=='__main__':run()
