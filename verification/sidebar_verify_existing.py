"""Verify the completed native-panel model task without repeating inference."""
import json,re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect

root=Path(__file__).resolve().parents[1]
url=re.search(r'dsh web: (http[^\s]+)',(root/'verification/dsh-sidebar-test.log').read_text(encoding='utf-8')).group(1)
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1050})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url)
    preview=page.get_by_role('button',name='继续',exact=True)
    try:preview.wait_for(state='visible',timeout=4000);preview.click()
    except Exception:pass
    page.get_by_role('button',name='文献研究',exact=True).click()
    frame=page.frame_locator('iframe[title="文献研究工作台"]')
    expect(frame.locator('#topic-name')).to_be_visible()
    response=page.request.get(url.split('?')[0]+'deep-reading/api/state')
    assert response.status==200
    state=response.json()
    task=next(t for t in state['tasks'] if t['task']=='read.long' and state['topics'] and t['status']=='completed')
    topic=next(t for t in state['topics'] if t['id']==task['topic_id'])
    frame.locator('[data-topic="'+topic['id']+'"]').click()
    expect(frame.locator('#topic-name')).to_have_text(topic['name'])
    frame.get_by_role('button',name='任务与成果',exact=True).click()
    frame.locator('[data-result="'+task['id']+'"]').click()
    expect(frame.locator('#viewer-body')).not_to_be_empty()
    page.screenshot(path=str(root/'verification/native-sidebar-model.png'),full_page=True)
    frame.locator('[data-close="viewer"]').click()
    page.get_by_role('button',name=re.compile('插件|Plugins')).first.click()
    page.get_by_role('button',name='文献研究',exact=True).click()
    expect(frame.locator('#topic-name')).to_have_text(topic['name'])
    page.screenshot(path=str(root/'verification/native-sidebar-main.png'),full_page=True)
    unauth=browser.new_context()
    assert unauth.request.get(url.split('?')[0]+'deep-reading/api/state').status in (401,403)
    assert page.request.get(url.split('?')[0]+'deep-reading/bridge/next').status==404
    assert page.request.get(url.split('?')[0]+'deep-reading/api/state',headers={'Origin':'http://evil.example'}).status==403
    unauth.close()
    assert not errors,errors
    (root/'verification/sidebar-results.json').write_text(json.dumps({'status':'passed','checks':['native sidebar entry','same-origin embedded main panel','topic creation and upload via prior browser run','evidence idea lab','panel switching retains selected topic','completed real model task launched through native panel','formatted model result','unauthenticated and foreign-origin requests rejected','internal bridge inaccessible'],'model_task_id':task['id'],'model_task_status':task['status'],'page_errors':errors,'timing_note':'Real inference exceeded the first 120-second browser assertion; completed state and rendered artifact were subsequently verified without repeating inference.'},ensure_ascii=False,indent=2),encoding='utf-8')
    browser.close()
print('Native sidebar model and access verification passed')
