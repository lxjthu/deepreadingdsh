"""Live acceptance driver; uses no API keys and never prints local access tokens."""
import argparse
import json
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
HOME=Path(r'D:\code\dsh-deep-reading-runtime\test-home')
config=json.loads((HOME/'connection.json').read_text(encoding='utf-8'))
REPORT=ROOT/'verification/live-results.json'


def api(path,body=None):
    request=urllib.request.Request(config['url']+path,data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8'),headers={'X-Reading-Token':config['token'],'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)


def wait(task_id,report,label):
    previous=None
    deadline=time.monotonic()+1200
    while time.monotonic()<deadline:
        row=next(t for t in api('/api/state')['tasks'] if t['id']==task_id)
        if row['status']!=previous:
            print(label,row['status'],flush=True);previous=row['status']
        if row['status'] in ('completed','failed','cancelled','interrupted'):
            report[label]=row
            REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            if row['status']!='completed':raise RuntimeError(label+': '+str(row['error']))
            return row
        time.sleep(2)
    raise TimeoutError(label)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--without-ocr',action='store_true');parser.add_argument('--continue-existing',action='store_true');args=parser.parse_args()
    inputs=ROOT/'verification/inputs';inputs.mkdir(exist_ok=True)
    text='''# Digitalization and firm productivity: a synthetic methods note

## Abstract
This is a synthetic paper used only to verify a literature reader. It is not a published empirical finding. Digitalization may improve productivity through information sharing. The proposed theory is the resource-based view. No causal effect has been estimated.

## Theory and mechanism
Digital capabilities can reduce information costs. Information sharing is a proposed mediator. Institutional context may moderate this relationship. These hypotheses require empirical verification.

## Data and measurement
A hypothetical panel covers manufacturing firms from 2015 to 2022. Productivity would be measured by value added per worker; digitalization by software investment divided by total assets. No real observations are provided.

## Identification and limitations
Firm and year fixed effects are a starting descriptive design. Reverse causality, measurement error and omitted variables remain concerns. The note has no natural experiment or valid instrumental variable. It cannot establish causality or novelty.

## References
Barney, J. (1991). Firm resources and sustained competitive advantage. Journal of Management, 17(1), 99-120.
'''
    md=inputs/'synthetic-paper.md';md.write_text(text,encoding='utf-8')
    import fitz
    pdf=fitz.open();page=pdf.new_page(width=595,height=842)
    page.insert_textbox(fitz.Rect(40,35,555,800),text,fontsize=11,fontname='helv')
    image=page.get_pixmap(dpi=150)
    raster=fitz.open();p=raster.new_page(width=595,height=842);p.insert_image(p.rect,pixmap=image);pdfpath=inputs/'synthetic-scanned-paper.pdf';raster.save(pdfpath);raster.close();pdf.close()
    report=json.loads(REPORT.read_text(encoding='utf-8')) if args.continue_existing else {'material':'self-authored synthetic methods note, not empirical evidence'}
    report['model_route']=config['model']
    topic=report['topic_id'] if args.continue_existing else api('/api/topics',{'name':'验收：数字化与企业生产率','description':'插件真实 OCR 与 dsh 模型调用验证；使用合成研究材料。'})['id']
    report['topic_id']=topic
    source=md if args.without_ocr else pdfpath
    imported=report['ocr_import'] if args.continue_existing else wait(api('/api/import',{'topic_id':topic,'path':str(source),'engine':'unlimited'})['id'],report,'ocr_import' if not args.without_ocr else 'md_import')
    entry=imported['result']['entry_ids'][0]
    second=inputs/'synthetic-second.md';second.write_text(text.replace('Digitalization and firm productivity','Organizational capability and firm productivity').replace('software investment divided by total assets','employee training expenditure per worker'),encoding='utf-8')
    second_result=report['second_import'] if args.continue_existing else wait(api('/api/import',{'topic_id':topic,'path':str(second)})['id'],report,'second_import')
    entry2=second_result['result']['entry_ids'][0]
    for task,question,ids in [
        ('read.quant','明确这是合成材料；未估计结果不得写成实证结论。',[entry]),
        ('references.extract','提取材料明确列出的参考文献。',[entry]),
        ('qa','本文采用了哪些识别方法？是否已经建立因果关系？',[entry]),
        ('compare','对比变量测量、机制与识别局限。',[entry,entry2]),
        ('idea-lab','',[entry,entry2]),
        ('idea-lab.deepen','沿用本主题已有构念，提出两个待检验研究设计，附原文证据和数据缺项。',[entry,entry2]),
    ]:
        if args.continue_existing and task in report:
            if report[task]['status']=='completed': continue
            task_id=report[task]['id'];api('/api/resume',{'id':task_id})
        else: task_id=api('/api/tasks',{'topic_id':topic,'task':task,'entry_ids':ids,'question':question})['id']
        wait(task_id,report,task)
    print('LIVE ACCEPTANCE COMPLETE',flush=True)


if __name__=='__main__':main()
