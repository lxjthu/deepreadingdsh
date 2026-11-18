import json
import re
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

root=Path(__file__).resolve().parents[1]
log=root/'verification/dsh-sidebar-test.log'
url=re.search(r'dsh web: (http[^\s]+)',log.read_text(encoding='utf-8')).group(1)
errors=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1600,'height':1050})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(url)
    try:
        preview=page.get_by_role('button',name='继续',exact=True)
        try:preview.wait_for(state='visible',timeout=5000);preview.click()
        except Exception:pass
        page.get_by_role('button',name='文献研究',exact=True).click(timeout=45000)
        expect(page.locator('[data-deep-reading-panel]')).to_be_visible()
        frame=page.frame_locator('iframe[title="文献研究工作台"]')
        expect(frame.locator('#topic-name')).to_be_visible(timeout=20000)
        frame.locator('#new-topic').click()
        name='侧栏验收 '+str(int(time.time()))
        frame.locator('#new-name').fill(name)
        frame.locator('#topic-form button.primary').click()
        expect(frame.locator('#topic-name')).to_have_text(name)
        frame.locator('#import-open').click()
        frame.locator('#import-file').set_input_files(str(root/'verification/inputs/synthetic-paper.md'))
        frame.locator('#import-submit').click()
        expect(frame.locator('#tasks')).to_contain_text('已完成',timeout=15000)
        frame.get_by_role('button',name='文献库',exact=True).click()
        expect(frame.locator('#papers input[type="checkbox"]')).to_have_count(1)
        frame.locator('#papers input[type="checkbox"]').check()
        frame.get_by_role('button',name='创意实验室',exact=True).click()
        frame.locator('#idea-run').click()
        expect(frame.locator('#tasks')).to_contain_text('经济管理创意实验室')
        expect(frame.locator('#tasks .task-row').first).to_contain_text('已完成',timeout=15000)
        frame.locator('#tasks button[data-result]').first.click()
        expect(frame.locator('#viewer-body')).to_contain_text('原文证据')
        page.screenshot(path=str(root/'verification/native-sidebar-result.png'),full_page=True)
        frame.locator('[data-close="viewer"]').click()
        page.get_by_role('button',name=re.compile('插件|Plugins')).first.click()
        page.get_by_role('button',name='文献研究',exact=True).click()
        expect(frame.locator('#topic-name')).to_have_text(name)
        frame.get_by_role('button',name='精读与分析',exact=True).click()
        frame.locator('#task').select_option('read.long')
        # Re-mounting intentionally clears transient checkboxes; choose explicitly.
        frame.get_by_role('button',name='文献库',exact=True).click()
        frame.locator('#papers input[type="checkbox"]').check()
        frame.get_by_role('button',name='精读与分析',exact=True).click()
        frame.locator('#dimensions').fill('理论框架')
        frame.locator('#run').click()
        expect(frame.locator('#tasks .task-row').first).to_contain_text('长文本维度精读',timeout=10000)
        expect(frame.locator('#tasks .task-row').first).to_contain_text('已完成',timeout=660000)
        page.screenshot(path=str(root/'verification/native-sidebar-main.png'),full_page=True)
        # Same-origin transport must retain dsh access checks.
        unauth=browser.new_context()
        assert unauth.request.get(url.split('?')[0]+'deep-reading/api/state').status in (401,403)
        unauth.close()
        assert not errors,errors
        result={'status':'passed','checks':['native sidebar entry','embedded main panel','topic creation','file upload','evidence idea lab','panel switching retains topic','native panel real model task','unauthenticated access rejected'],'page_errors':errors}
        (root/'verification/sidebar-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Native sidebar acceptance passed')
    except Exception:
        page.screenshot(path=str(root/'verification/sidebar-failure.png'),full_page=True)
        (root/'verification/sidebar-errors.json').write_text(json.dumps({'errors':errors,'body':page.locator('body').inner_text()[:10000]},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    finally: browser.close()
