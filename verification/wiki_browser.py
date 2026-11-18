"""Headless browser acceptance on temporary, explicitly synthetic local sources."""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from server import Store,Handler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright,expect

os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',r'C:\Users\langx\AppData\Local\ms-playwright')
OUT=Path(__file__).parent

def run():
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);s=Store(root/'home');topic=s.create_topic('隔离的浏览器验收样例')['id']
        ids=[]
        for i in range(2):
            paper=root/f'paper{i}.md'
            paper.write_text(f'# 中文长标题：跨论文研究知识整合与不同测量方式的核对示例第{i}篇\n\n本文采用资源基础观；使用CFPS数据库。数字化采用投入比例测量。\n量表修订版用于本研究，信度0.8。案例边界为2020至2021年。\n',encoding='utf-8')
            ids.append(s.import_file({'topic_id':topic,'path':str(paper)},'browser')['entry_ids'][0])
        rs={}
        for kind,name,relation in [('theory','资源基础观','adopts'),('method','固定效应','mentions'),('variable','数字化','measures'),('author','张伟','cites'),('dataset','CFPS','uses'),('scale','测量量表修订版','uses'),('case','同一组织的特定时期案例','studies')]:
            body={'kind':kind,'name':name,'relation':relation,'details':{'role':'自变量','operationalization':'投入比例','dataset':'CFPS','sample':'制造业','limitations':'仅本研究情境'},'evidence':[{'quote':'本文采用资源基础观；使用CFPS数据库。'}]}
            r=s.wiki.propose(ids[0],body);rs[kind]=r
        b={'kind':'variable','name':'数字化','relation':'measures','details':{'role':'中介变量','operationalization':'词频','dataset':'CFPS','sample':'不同行业'},'evidence':[{'quote':'数字化采用投入比例测量。'}]}
        r2=s.wiki.propose(ids[1],b)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.store=s;server.token='isolated-browser-fixture';server.base=f'http://127.0.0.1:{server.server_address[1]}'
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        s.model_call=lambda *_:{'content':'{"records":[]}','finish_reason':'stop'}
        worker=threading.Thread(target=s.worker,daemon=True);worker.start()
        try:
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True)
                try:
                    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(server.base+'/#'+server.token);expect(page.locator('#papers .paper')).to_have_count(2)
                    page.locator('[data-select]').first.check()
                    page.get_by_role('button',name='研究 Wiki',exact=True).click()
                    page.locator('#wiki-extract').click()
                    expect(page.locator('#tasks')).to_contain_text('已完成',timeout=15000)
                    expect(page.locator('#tasks')).to_contain_text('全文分段 1 / 1')
                    page.get_by_role('button',name='研究 Wiki',exact=True).click()
                    expect(page.locator('#wiki-list .wiki-item')).to_have_count(7)
                    # All seven types are real pages backed by fixture records.
                    for kind,r in rs.items():
                        page.locator(f'[data-wiki-entity="{r["entity_id"]}"]').first.click()
                        expect(page.locator('#wiki-page h2')).to_be_visible()
                    page.locator(f'[data-wiki-entity="{rs["variable"]["entity_id"]}"]').first.click()
                    expect(page.locator('[data-wiki-candidate]')).to_have_count(2)
                    for box in page.locator('[data-wiki-candidate]').all():box.check()
                    page.locator('#wiki-confirm-batch').click()
                    expect(page.locator('#wiki-page .wiki-record.confirmed')).to_have_count(2)
                    expect(page.locator('#wiki-page table tbody tr')).to_have_count(2)
                    expect(page.locator('#wiki-page table')).to_contain_text('中介变量')
                    expect(page.locator('#wiki-page table')).to_contain_text('词频')
                    page.locator('#wiki-edit-entity').click();page.locator('#wiki-edit-note').fill('浏览器保存的人工笔记')
                    page.locator('#wiki-editor-save').click();expect(page.locator('.wiki-note')).to_have_text('浏览器保存的人工笔记')
                    page.locator('[data-wiki-record-edit]').first.click();page.locator('[data-wiki-field="role"]').fill('调节变量')
                    page.locator('#wiki-editor-save').click();expect(page.locator('#wiki-page table')).to_contain_text('调节变量')
                    page.locator('[data-wiki-evidence]').first.click();expect(page.locator('#viewer-body')).to_contain_text('本文采用资源基础观')
                    page.locator('[data-close="viewer"]').click()
                    page.locator('[data-wiki-paper]').first.click();expect(page.locator('#library-detail')).to_be_visible()
                    expect(page.locator('#entry-wiki button')).not_to_have_count(0)
                    page.locator('#entry-wiki [data-wiki-entity]').first.click();expect(page.locator('#library-detail')).not_to_be_visible()
                    # Candidate diff and manual association have a native form with full search.
                    page.locator(f'[data-wiki-entity="{rs["theory"]["entity_id"]}"]').first.click()
                    page.locator('[data-wiki-relink]').click();page.locator('#wiki-target-query').fill('资源基础观');page.locator('#wiki-target-search').click()
                    expect(page.locator('#wiki-target-count')).to_contain_text('1 个结果')
                    page.locator('[data-close="wiki-editor"]').click()
                    page.locator(f'[data-wiki-entity="{rs["variable"]["entity_id"]}"]').first.click()
                    page.locator('[data-wiki-restore]').last.click()
                    expect(page.locator('.wiki-candidate')).to_contain_text('恢复历史版本')
                    page.locator('.wiki-candidate summary').click();expect(page.locator('.wiki-candidate')).to_contain_text('恢复版本')
                    page.locator('[data-wiki-candidate]').check();page.locator('#wiki-confirm-batch').click()
                    expect(page.locator('.wiki-note')).to_have_text('暂无人工笔记')
                    page.screenshot(path=str(OUT/'wiki-desktop.png'),full_page=True)
                    page.set_viewport_size({'width':480,'height':900})
                    expect(page.locator('#wiki-extract')).to_be_visible()
                    page.screenshot(path=str(OUT/'wiki-narrow.png'),full_page=True)
                    width=page.evaluate('({body:document.body.scrollWidth,viewport:innerWidth})')
                    assert width['body']<=width['viewport']+2,width
                    assert not errors,errors
                    report={'selected_extraction_task':True,'seven_entity_types':True,'candidate_batch_review':True,'measurement_comparison':True,
                            'manual_edit':True,'evidence_location':True,'paper_backlinks':True,'candidate_relink_search':True,
                            'history_restore_review':True,'narrow_width':width,'page_errors':errors,'source':'synthetic isolated fixtures; no live model'}
                    (OUT/'wiki-browser-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                    print(json.dumps(report,ensure_ascii=False))
                finally:browser.close()
        finally:s.stop.set();server.shutdown();server.server_close();thread.join(3);worker.join(3)

if __name__=='__main__':run()
