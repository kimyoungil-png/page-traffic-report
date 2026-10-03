from __future__ import annotations

import io, os, tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_AUTO_SIZE, PP_ALIGN
from pptx.util import Pt

CHANNEL_ROWS=["App","Organic Search","Direct","Referral","Owned Social","Social Network","CRM","Paid Search","Display AD","Total"]
R_NS="{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
ROOT=Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE_PATH=ROOT/'templates'/'pd_bc_sample.pptx'
FONT='Meiryo UI'; BLACK=RGBColor(0,0,0); BLUE=RGBColor(30,53,227); RBLUE=RGBColor(0,49,244); RED=RGBColor(255,0,0); GREY=RGBColor(128,128,128); PALE=RGBColor(181,181,181)


def _load(): return Presentation(str(DEFAULT_TEMPLATE_PATH))

def _dup(prs,src):
    ns=prs.slides.add_slide(src.slide_layout)
    for sh in list(ns.shapes): sh.element.getparent().remove(sh.element)
    for sh in src.shapes:
        cloned=deepcopy(sh.element); rid_map={}
        for el in cloned.iter():
            for attr in (R_NS+'embed',R_NS+'link',R_NS+'id'):
                rid=el.get(attr)
                if not rid or rid not in src.part.rels: continue
                if rid not in rid_map:
                    rel=src.part.rels[rid]; rid_map[rid]=ns.part.relate_to(rel._target,rel.reltype)
                el.set(attr,rid_map[rid])
        ns.shapes._spTree.insert_element_before(cloned,'p:extLst')
    return ns

def _remove_slide(prs,idx):
    el=prs.slides._sldIdLst[idx]; prs.part.drop_rel(el.rId); del prs.slides._sldIdLst[idx]

def _find_text(slide,pred):
    for sh in slide.shapes:
        if hasattr(sh,'text') and pred(sh.text or '',sh): return sh

def _find_table(slide,r,c):
    for sh in slide.shapes:
        if sh.has_table and len(sh.table.rows)==r and len(sh.table.columns)==c: return sh.table

def _font(run,size=None,color=None,bold=None):
    run.font.name=FONT
    if size is not None: run.font.size=Pt(size)
    if color is not None: run.font.color.rgb=color
    if bold is not None: run.font.bold=bold

def _set_shape(sh,text,size=None,color=None,bold=None):
    tf=sh.text_frame; tf.clear(); tf.word_wrap=True; tf.auto_size=MSO_AUTO_SIZE.NONE
    r=tf.paragraphs[0].add_run(); r.text=str(text or ''); _font(r,size,color,bold)

def _set_cell(cell,text,size=7.5,color=None,bold=None):
    tf=cell.text_frame; tf.clear(); tf.auto_size=MSO_AUTO_SIZE.NONE
    p=tf.paragraphs[0]; p.alignment=PP_ALIGN.CENTER
    r=p.add_run(); r.text=str(text or ''); _font(r,size,color,bold)

def _num(v): return f'{int(round(float(v or 0))):,}'
def _compact(v):
    v=float(v or 0)
    if abs(v)>=10000: return f'{v/1000:.0f}K'
    if abs(v)>=950: return f'{v/1000:.1f}K'
    return f'{int(round(v)):,}'
def _pct(v,d=1): return '—' if v is None else f'{float(v):.{d}f}%'
def _ratio(c,p): return ('NEW' if c else '—') if not p else f'x{float(c)/float(p):.2f}'
def _ratio_color(s):
    try:return RED if float(str(s).replace('x',''))<1 else RBLUE
    except:return GREY

def _fill_title(slide,p):
    sh=_find_text(slide,lambda t,s:'PD Visit' in t and 'BC Visit' in t)
    if not sh:return
    total=p['main']['Total']; prev=total['previous']; curr=total['current']; name=p['product_name']
    pr=_ratio(curr['pd_visit'],prev['pd_visit']); br=_ratio(curr['bc_visit'],prev['bc_visit']); vr=_ratio(curr['piv_total'],prev['piv_total'])
    deltas=[]
    for ch in CHANNEL_ROWS[:-1]:
        row=p['main'].get(ch,{})
        if row: deltas.append((ch,row['current']['pd_visit']-row['previous']['pd_visit']))
    total_delta=curr['pd_visit']-prev['pd_visit']
    if total_delta<0 and deltas:
        top=min(deltas,key=lambda x:x[1]); insight=f'{top[0]}からのPD流入が減少'
    elif total_delta>0 and deltas:
        top=max(deltas,key=lambda x:x[1]); insight=f'{top[0]}からのPD流入が増加'
    else: insight='PD流入は前週並み'
    tf=sh.text_frame; tf.clear(); tf.word_wrap=True; tf.auto_size=MSO_AUTO_SIZE.NONE
    p0=tf.paragraphs[0]
    for txt,color,size in [(f'{name} PD Visit {_compact(curr["pd_visit"])} (',BLACK,18),(pr,_ratio_color(pr),16),(' vs 先週) ',BLACK,16),(f'→ {insight}',BLUE,14)]:
        r=p0.add_run(); r.text=txt; _font(r,size,color,True)
    p1=tf.add_paragraph()
    for txt,color,size in [(f'{name} BC Visit {_compact(curr["bc_visit"])} (',BLACK,18),(br,_ratio_color(br),16),(' vs 先週) , PIV ',BLACK,16),(f'{_compact(curr["piv_total"])}件 (',BLACK,18),(vr,_ratio_color(vr),16),(' vs 先週)',BLACK,16)]:
        r=p1.add_run(); r.text=txt; _font(r,size,color,True)

def _fill_bullets(slide,p):
    sh=_find_text(slide,lambda t,s:'流入割合' in t)
    if not sh:return
    total=p['main']['Total']['current']['bc_visit']; shares=[]
    for ch in CHANNEL_ROWS[:-1]:
        val=p['main'].get(ch,{}).get('current',{}).get('bc_visit',0); shares.append((ch,val,val/total*100 if total else 0))
    shares.sort(key=lambda x:x[1],reverse=True); disp={'Organic Search':'Organic'}
    line1='流入割合：'+' > '.join(f'{disp.get(ch,ch)} {pct:.0f}%' for ch,_,pct in shares[:3])
    prev=p['main']['Total']['previous']['pir']; curr=p['main']['Total']['current']['pir']
    line2=f'PIR：先週 {_pct(prev,1)} → 今週 {_pct(curr,1)}'
    parts=[]
    for label in ('Galaxy','iPhone','Sony Xperia'):
        row=p['device_summary'].get(label,{}); parts.append(f'{label} {_compact(row.get("piv_total",0))}件 (PIR {_pct(row.get("pir"),1)})')
    line3='PIV端末別：'+'、'.join(parts)
    tf=sh.text_frame; tf.clear(); tf.word_wrap=True; tf.auto_size=MSO_AUTO_SIZE.NONE
    for i,line in enumerate((line1,line2,line3)):
        par=tf.paragraphs[0] if i==0 else tf.add_paragraph(); r=par.add_run(); r.text=line; _font(r,11,BLACK,False)

def _fill_summary_table(slide,p):
    t=_find_table(slide,12,17)
    if not t: raise RuntimeError('Summary table not found')
    name=p['product_name']; _set_cell(t.cell(0,0),name+'\nPD+BC',8,BLACK,True); _set_cell(t.cell(0,8),f'Last Week ({p["short_period_label"]})',8,BLACK,True)
    _set_cell(t.cell(1,7),name+'\nOrder',7,BLACK,True); _set_cell(t.cell(1,16),name+' Order',7,BLACK,True)
    for ri,ch in enumerate(CHANNEL_ROWS,start=2):
        row=p['main'].get(ch)
        if not row: continue
        a=row['previous']; b=row['current']; pr=_ratio(b['pd_visit'],a['pd_visit']); br=_ratio(b['bc_visit'],a['bc_visit'])
        vals=[ch,_num(a['pd_visit']),_num(a['pd_to_bc']),_num(a['bc_visit']),_num(a['carrier_piv']),_num(a['estore_piv']),_pct(a['pir'],1),_num(a['order']),_num(b['pd_visit']),pr,_num(b['pd_to_bc']),_num(b['bc_visit']),br,_num(b['carrier_piv']),_num(b['estore_piv']),_pct(b['pir'],1),_num(b['order'])]
        for ci,val in enumerate(vals):
            color=GREY if ci in (1,2,3,4,5,6,7) else BLACK
            if ci in (9,12): color=_ratio_color(val)
            _set_cell(t.cell(ri,ci),val,7 if ci else 6.8,color,(ch=='Total' or ci in (9,12)))

def _fill_carriers(slide,p):
    boxes=[sh for sh in slide.shapes if hasattr(sh,'text') and (sh.text or '').strip().startswith('docomo')]; boxes.sort(key=lambda s:s.left)
    for sh,key in zip(boxes,('2 weeks ago','Last Week')):
        d=p['piv_detail'].get(key,{})
        _set_shape(sh,f'docomo {_num(d.get("docomo"))}\nau {_num(d.get("au"))}\nSoftBank {_num(d.get("softbank"))}\nRakuten {_num(d.get("rakuten"))}',8,BLACK,True)

def _fill_summary_meta(slide,p):
    label=_find_text(slide,lambda t,s:t.strip().endswith('PD+BC Page') and 'Visit' not in t)
    if label:_set_shape(label,f'{p["product_name"]} PD+BC Page',10,PALE,True)
    footer=_find_text(slide,lambda t,s:'Data：' in t and 'samsung.com' in t)
    if footer:_set_shape(footer,f'Data：{p["period_label"]}\n{p["url"]}、{p["url"].rstrip("/")}/buy/',6.4,GREY,False)

def _replace_screenshot(slide,p):
    data=p.get('screenshot_bytes')
    if not data:return
    target=next((sh for sh in slide.shapes if sh.shape_type==13 and sh.left<3000000 and sh.top>1800000),None)
    if not target:return
    left,top,width,height=target.left,target.top,target.width,target.height; target.element.getparent().remove(target.element)
    with tempfile.NamedTemporaryFile(suffix='.png',delete=False) as f:f.write(data); path=f.name
    try:slide.shapes.add_picture(path,left,top,width=width,height=height)
    finally: os.remove(path)

def _rate(row,key):
    base=row.get('bc_visit',0); return row.get(key,0)/base*100 if base else None

def _fill_funnel(slide,p):
    name=p['product_name']; bcname=('Z '+name if (name.startswith('Fold') or name.startswith('Flip')) else name)
    h=_find_text(slide,lambda t,s:'BC Page 経路' in t)
    if h:_set_shape(h,f'{bcname} BC Page 経路',10,PALE,True)
    title=_find_text(slide,lambda t,s:'購入経路' in t)
    if title:_set_shape(title,f'{name} BCからOrderまでの購入経路',18,BLACK,True)
    b=_find_text(slide,lambda t,s:'CVR' in t)
    if b:
        cur=p['funnel']['current']; prev=p['funnel']['previous']
        lines=[]
        for seg,label in [('Organic Search','Organic'),('Paid','Paid')]:
            a=prev.get(seg,{}); c=cur.get(seg,{})
            pc=(a.get('order',0)/a.get('bc_visit',1)*100) if a.get('bc_visit') else None
            cc=(c.get('order',0)/c.get('bc_visit',1)*100) if c.get('bc_visit') else None
            lines.append(f'{label} のBC VisitからOrderまでのCVRは 先週 {_pct(pc,2)} → 今週 {_pct(cc,2)}')
        tf=b.text_frame; tf.clear(); tf.word_wrap=True; tf.auto_size=MSO_AUTO_SIZE.NONE
        for i,line in enumerate(lines):
            par=tf.paragraphs[0] if i==0 else tf.add_paragraph(); r=par.add_run(); r.text=line; _font(r,11,BLACK,False)
    footer=_find_text(slide,lambda t,s:'Data：' in t)
    if footer:
        ds=p['date_start'].split('-'); de=p['date_end'].split('-'); _set_shape(footer,f'Data：{int(ds[0])}/{int(ds[1])}/{int(ds[2])} ~ {int(de[1])}/{int(de[2])}',6.4,GREY,False)
    t=_find_table(slide,19,11)
    if not t:raise RuntimeError('Funnel table not found')
    keys=['bc_visit','cart_add_event','add_on_visit','cart_page_visit','checkout_login','contact_info','delivery','payment',None,'order_confirmation','order']
    starts={'Organic Search':2,'Other':8,'Paid':14}
    for seg,sr in starts.items():
        c=p['funnel']['current'].get(seg,{}); a=p['funnel']['previous'].get(seg,{})
        for ci,key in enumerate(keys):
            if key is None:
                for rr in (sr,sr+1,sr+3,sr+4): _set_cell(t.cell(rr,ci),'',6,GREY,False)
                continue
            _set_cell(t.cell(sr,ci),_num(c.get(key)) if c.get(key) else '',13,RBLUE if seg=='Paid' else GREY,True)
            prev_abs = key in {'bc_visit','cart_add_event','cart_page_visit','order'}
            _set_cell(t.cell(sr+1,ci),f'(先週：{_num(a.get(key))})' if prev_abs and a.get(key) else '',6,GREY,True)
            if key=='bc_visit':
                _set_cell(t.cell(sr+3,ci),'移動率',6.5,RBLUE if seg=='Paid' else GREY,True); _set_cell(t.cell(sr+4,ci),'先週',6.5,RBLUE if seg=='Paid' else GREY,True)
            else:
                _set_cell(t.cell(sr+3,ci),_pct(_rate(c,key),1),6.5,RBLUE if seg=='Paid' else GREY,True)
                _set_cell(t.cell(sr+4,ci),_pct(_rate(a,key),1),6.5,RBLUE if seg=='Paid' else GREY,True)

def _no_autofit(slide):
    for sh in slide.shapes:
        if hasattr(sh,'text_frame') and sh.has_text_frame: sh.text_frame.auto_size=MSO_AUTO_SIZE.NONE

def _fill_summary(slide,p):
    _fill_title(slide,p); _fill_bullets(slide,p); _fill_summary_table(slide,p); _fill_carriers(slide,p); _fill_summary_meta(slide,p); _replace_screenshot(slide,p); _no_autofit(slide)

def build_pd_bc_report(products:list[dict[str,Any]])->bytes:
    prs=_load(); s1=prs.slides[0]; s2=prs.slides[1]
    for p in products:
        ns=_dup(prs,s1); _fill_summary(ns,p)
        if p.get('funnel',{}).get('current'):
            nf=_dup(prs,s2); _fill_funnel(nf,p); _no_autofit(nf)
    _remove_slide(prs,0); _remove_slide(prs,0)
    bio=io.BytesIO(); prs.save(bio); return bio.getvalue()
