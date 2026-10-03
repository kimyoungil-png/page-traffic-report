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
BLACK=RGBColor(0,0,0); BLUE=RGBColor(30,53,227); RBLUE=RGBColor(0,49,244); RED=RGBColor(255,0,0); GREY=RGBColor(128,128,128); PALE=RGBColor(181,181,181); WHITE=RGBColor(255,255,255)


def _load():
    return Presentation(str(DEFAULT_TEMPLATE_PATH))


def _dup(prs,src):
    ns=prs.slides.add_slide(src.slide_layout)
    for sh in list(ns.shapes):
        sh.element.getparent().remove(sh.element)
    for sh in src.shapes:
        cloned=deepcopy(sh.element)
        rid_map={}
        for el in cloned.iter():
            for attr in (R_NS+'embed', R_NS+'link', R_NS+'id'):
                rid=el.get(attr)
                if not rid or rid not in src.part.rels:
                    continue
                if rid not in rid_map:
                    rel=src.part.rels[rid]
                    rid_map[rid]=ns.part.relate_to(rel._target, rel.reltype)
                el.set(attr, rid_map[rid])
        ns.shapes._spTree.insert_element_before(cloned, 'p:extLst')
    return ns


def _remove_slide(prs,idx):
    el=prs.slides._sldIdLst[idx]
    prs.part.drop_rel(el.rId)
    del prs.slides._sldIdLst[idx]


def _find_text(slide,pred):
    for sh in slide.shapes:
        if hasattr(sh,'text') and pred(sh.text or '', sh):
            return sh


def _find_table(slide,r,c):
    for sh in slide.shapes:
        if sh.has_table and len(sh.table.rows)==r and len(sh.table.columns)==c:
            return sh.table


def _run_style(run) -> dict[str, Any]:
    font=run.font
    color=None
    try:
        color=font.color.rgb
    except Exception:
        color=None
    return {
        'name': font.name,
        'size': font.size,
        'bold': font.bold,
        'italic': font.italic,
        'color': color,
    }


def _text_frame_styles(tf) -> list[dict[str, Any]]:
    styles=[]
    for p in tf.paragraphs:
        for r in p.runs:
            styles.append(_run_style(r))
    return styles


def _first_style(tf, fallback_size=None) -> dict[str, Any]:
    styles=_text_frame_styles(tf)
    if styles:
        return styles[0]
    return {'name': None, 'size': fallback_size, 'bold': None, 'italic': None, 'color': None}


def _apply_style(run, style: dict[str, Any] | None, *, color=None, bold=None):
    style=style or {}
    if style.get('name'):
        run.font.name=style['name']
    if style.get('size') is not None:
        run.font.size=style['size']
    if color is not None:
        run.font.color.rgb=color
    elif style.get('color') is not None:
        run.font.color.rgb=style['color']
    if bold is not None:
        run.font.bold=bold
    elif style.get('bold') is not None:
        run.font.bold=style['bold']
    if style.get('italic') is not None:
        run.font.italic=style['italic']


def _set_shape(sh,text,size=None,color=None,bold=None):
    # Preserve the template run size/name. Fallback size is only used if the template has no run style.
    style=_first_style(sh.text_frame, fallback_size=size)
    tf=sh.text_frame
    tf.clear()
    tf.word_wrap=True
    tf.auto_size=MSO_AUTO_SIZE.NONE
    r=tf.paragraphs[0].add_run()
    r.text=str(text or '')
    _apply_style(r, style, color=color, bold=bold)


def _set_cell(cell,text,size=7.5,color=None,bold=None):
    # Preserve the original cell font size from the template instead of applying a hard-coded size.
    style=_first_style(cell.text_frame, fallback_size=None)
    tf=cell.text_frame
    tf.clear()
    tf.auto_size=MSO_AUTO_SIZE.NONE
    p=tf.paragraphs[0]
    p.alignment=PP_ALIGN.CENTER
    r=p.add_run()
    r.text=str(text or '')
    _apply_style(r, style, color=color, bold=bold)


def _clear_paragraph_preserve_style(paragraph):
    p_element=paragraph._p
    for child in list(p_element):
        if child.tag.endswith('}pPr'):
            continue
        p_element.remove(child)


def _ensure_styled_paragraph(text_frame,index):
    while len(text_frame.paragraphs)<=index:
        new_p=text_frame.add_paragraph()
        base_p_pr=text_frame.paragraphs[0]._p.pPr
        if base_p_pr is not None:
            if new_p._p.pPr is not None:
                new_p._p.remove(new_p._p.pPr)
            new_p._p.insert(0,deepcopy(base_p_pr))
    return text_frame.paragraphs[index]


def _set_paragraph_text_preserve_style(paragraph,text,style,color=BLACK,bold=False):
    _clear_paragraph_preserve_style(paragraph)
    r=paragraph.add_run()
    r.text=str(text or '')
    _apply_style(r,style,color=color,bold=bold)


def _num(v):
    return f'{int(round(float(v or 0))):,}'


def _compact(v):
    v=float(v or 0)
    if abs(v)>=10000:
        return f'{v/1000:.0f}K'
    if abs(v)>=950:
        return f'{v/1000:.1f}K'
    return f'{int(round(v)):,}'


def _pct(v,d=1):
    return '—' if v is None else f'{float(v):.{d}f}%'


def _ratio(c,p):
    return ('NEW' if c else '—') if not p else f'x{float(c)/float(p):.2f}'


def _ratio_color(s):
    try:
        return RED if float(str(s).replace('x',''))<1 else RBLUE
    except Exception:
        return GREY


def _add_run(paragraph, text, style, color=None, bold=None):
    r=paragraph.add_run()
    r.text=text
    _apply_style(r, style, color=color, bold=bold)


def _fill_title(slide,p):
    sh=_find_text(slide,lambda t,s:'PD Visit' in t and 'BC Visit' in t)
    if not sh:
        return

    total=p['main']['Total']
    prev=total['previous']
    curr=total['current']
    name=p['product_name']

    pr=_ratio(curr['pd_visit'],prev['pd_visit'])
    br=_ratio(curr['bc_visit'],prev['bc_visit'])
    vr=_ratio(curr['piv_total'],prev['piv_total'])

    deltas=[]
    for ch in CHANNEL_ROWS[:-1]:
        row=p['main'].get(ch,{})
        if row:
            deltas.append(
                (
                    ch,
                    row['current']['pd_visit']
                    - row['previous']['pd_visit'],
                )
            )

    total_delta=curr['pd_visit']-prev['pd_visit']
    if total_delta<0 and deltas:
        top=min(deltas,key=lambda x:x[1])
        fallback_insight=f'{top[0]}からのPD流入が減少'
    elif total_delta>0 and deltas:
        top=max(deltas,key=lambda x:x[1])
        fallback_insight=f'{top[0]}からのPD流入が増加'
    else:
        fallback_insight='PD流入は前週並み'

    insight=(
        p.get('analysis',{}).get('headline_comment')
        or fallback_insight
    )

    tf=sh.text_frame
    tf.clear()
    tf.word_wrap=True
    tf.auto_size=MSO_AUTO_SIZE.NONE

    # Line 1: PD Visit
    p0=tf.paragraphs[0]
    p0.space_after=Pt(0)

    r=p0.add_run()
    r.text=f'{name} PD Visit {_compact(curr["pd_visit"])} '
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(18)

    r=p0.add_run()
    r.text='('
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(14)

    r=p0.add_run()
    r.text=pr
    _apply_style(r,None,color=_ratio_color(pr),bold=True)
    r.font.size=Pt(14)

    r=p0.add_run()
    r.text=' vs 先週)'
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(14)

    # Line 2: BC Visit / PIV
    p1=tf.add_paragraph()
    p1.space_before=Pt(0)
    p1.space_after=Pt(0)

    r=p1.add_run()
    r.text=f'{name} BC Visit {_compact(curr["bc_visit"])} '
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(18)

    r=p1.add_run()
    r.text='('
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(14)

    r=p1.add_run()
    r.text=br
    _apply_style(r,None,color=_ratio_color(br),bold=True)
    r.font.size=Pt(14)

    r=p1.add_run()
    r.text=' vs 先週) , PIV '
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(18)

    r=p1.add_run()
    r.text=f'{_compact(curr["piv_total"])}件 '
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(18)

    r=p1.add_run()
    r.text='('
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(14)

    r=p1.add_run()
    r.text=vr
    _apply_style(r,None,color=_ratio_color(vr),bold=True)
    r.font.size=Pt(14)

    r=p1.add_run()
    r.text=' vs 先週)'
    _apply_style(r,None,color=BLACK,bold=True)
    r.font.size=Pt(14)

    # Line 3: AI comment
    p2=tf.add_paragraph()
    p2.space_before=Pt(0)
    p2.space_after=Pt(0)

    r=p2.add_run()
    r.text=f'→ {insight}'
    _apply_style(r,None,color=BLUE,bold=True)
    r.font.size=Pt(14)


def _fill_bullets(slide,p):
    sh=_find_text(slide,lambda t,s:'流入割合' in t)
    if not sh:
        return

    styles=_text_frame_styles(sh.text_frame)
    base_style=styles[0] if styles else None

    total=p['main']['Total']['current']['bc_visit']
    shares=[]
    for ch in CHANNEL_ROWS[:-1]:
        val=(
            p['main']
            .get(ch,{})
            .get('current',{})
            .get('bc_visit',0)
        )
        shares.append(
            (
                ch,
                val,
                val/total*100 if total else 0,
            )
        )

    shares.sort(
        key=lambda x:x[1],
        reverse=True,
    )
    disp={'Organic Search':'Organic'}
    line1='流入割合：'+' > '.join(
        f'{disp.get(ch,ch)} {pct:.0f}%'
        for ch,_,pct in shares[:3]
    )

    prev=p['main']['Total']['previous']['pir']
    curr=p['main']['Total']['current']['pir']
    line2=(
        f'PIR：先週 {_pct(prev,1)} '
        f'→ 今週 {_pct(curr,1)}'
    )

    ranking=p.get('device_ranking',[])
    if not ranking:
        ranking=[]
        for label,periods in p.get(
            'device_summary',
            {},
        ).items():
            current_row=(
                periods.get('current',{})
                if isinstance(periods,dict)
                else {}
            )
            ranking.append(
                {
                    'name':label,
                    **current_row,
                }
            )
        ranking.sort(
            key=lambda row:(
                row.get('piv_total',0),
                row.get('visits',0),
            ),
            reverse=True,
        )

    parts=[]
    for row in ranking[:3]:
        label=row.get('name','')
        parts.append(
            f'{label} '
            f'{_compact(row.get("piv_total",0))}件 '
            f'(PIR {_pct(row.get("pir"),1)})'
        )
    line3='PIV端末別：'+'、'.join(parts)

    # Same treatment as Explore report:
    # do not clear the text frame; preserve each paragraph's pPr
    # so the template's real bullet/indent/spacing remains intact.
    tf=sh.text_frame
    tf.word_wrap=True
    tf.auto_size=MSO_AUTO_SIZE.NONE

    for index,line in enumerate(
        (line1,line2,line3)
    ):
        paragraph=_ensure_styled_paragraph(
            tf,
            index,
        )
        style=(
            styles[index]
            if index<len(styles)
            else base_style
        )
        _set_paragraph_text_preserve_style(
            paragraph,
            line,
            style,
            color=BLACK,
            bold=False,
        )

    for paragraph in tf.paragraphs[3:]:
        _set_paragraph_text_preserve_style(
            paragraph,
            '',
            base_style,
            color=BLACK,
            bold=False,
        )


def _fill_summary_table(slide,p):
    t=_find_table(slide,12,17)
    if not t:
        raise RuntimeError('Summary table not found')
    name=p['product_name']
    _set_cell(t.cell(0,0),name+'\nPD+BC',color=BLACK,bold=True)

    previous_group_title=t.cell(0,1).text or '2 Weeks ago'
    _set_cell(
        t.cell(0,1),
        previous_group_title,
        color=GREY,
        bold=True,
    )
    for ci in range(1,8):
        existing=t.cell(1,ci).text
        if ci==7:
            existing=name+'\nOrder'
        _set_cell(
            t.cell(1,ci),
            existing,
            color=GREY,
            bold=True,
        )

    _set_cell(
        t.cell(0,8),
        f'Last Week ({p["short_period_label"]})',
        color=BLACK,
        bold=True,
    )
    _set_cell(t.cell(1,16),name+' Order',color=BLACK,bold=True)
    for ri,ch in enumerate(CHANNEL_ROWS,start=2):
        row=p['main'].get(ch)
        if not row:
            continue
        a=row['previous']; b=row['current']; pr=_ratio(b['pd_visit'],a['pd_visit']); br=_ratio(b['bc_visit'],a['bc_visit'])
        vals=[ch,_num(a['pd_visit']),_num(a['pd_to_bc']),_num(a['bc_visit']),_num(a['carrier_piv']),_num(a['estore_piv']),_pct(a['pir'],1),_num(a['order']),_num(b['pd_visit']),pr,_num(b['pd_to_bc']),_num(b['bc_visit']),br,_num(b['carrier_piv']),_num(b['estore_piv']),_pct(b['pir'],1),_num(b['order'])]
        for ci,val in enumerate(vals):
            color=GREY if ci in (1,2,3,4,5,6,7) else BLACK
            if ci in (9,12):
                color=_ratio_color(val)
            _set_cell(t.cell(ri,ci),val,color=color,bold=(ch=='Total' or ci in (9,12)))


def _carrier_display_name(name):
    labels={
        'docomo': 'docomo',
        'au': 'au',
        'softbank': 'SoftBank',
        'rakuten': 'Rakuten',
        'jcom': 'J:COM',
    }
    return labels.get(name, name.replace('_', ' ').title())


def _fill_carriers(slide,p):
    boxes=[
        sh
        for sh in slide.shapes
        if hasattr(sh,'text')
        and (sh.text or '').strip().startswith('docomo')
    ]
    boxes.sort(key=lambda shape: shape.left)
    if not boxes:
        return

    detail=p.get('piv_detail', {})
    summary=detail.get('summary', {})
    previous=summary.get('previous', {})
    current=summary.get('current', {})

    order=detail.get('carrier_order', [])
    if not order:
        order=['docomo','au','softbank','rakuten','jcom']

    active=[]
    for carrier in order:
        previous_value=(
            previous.get('carriers', {}).get(carrier, 0)
            if isinstance(previous.get('carriers', {}), dict)
            else 0
        )
        current_value=(
            current.get('carriers', {}).get(carrier, 0)
            if isinstance(current.get('carriers', {}), dict)
            else 0
        )
        if previous_value or current_value:
            active.append(carrier)

    for shape, period_data in zip(
        boxes,
        (previous, current),
    ):
        lines=[]
        carriers=period_data.get('carriers', {})
        for carrier in active:
            lines.append(
                f'{_carrier_display_name(carrier)} '
                f'{_num(carriers.get(carrier, 0))}'
            )
        _set_shape(
            shape,
            '\n'.join(lines),
            color=BLACK,
            bold=True,
        )

def _fill_summary_meta(slide,p):
    label=_find_text(slide,lambda t,s:t.strip().endswith('PD+BC Page') and 'Visit' not in t)
    if label:
        _set_shape(label,f'{p["product_name"]} PD+BC Page',color=PALE,bold=True)
    footer=_find_text(slide,lambda t,s:'Data：' in t and 'samsung.com' in t)
    if footer:
        _set_shape(footer,f'Data：{p["period_label"]}\n{p["url"]}、{p["url"].rstrip("/")}/buy/',color=GREY,bold=False)


def _replace_screenshot(slide,p):
    data=p.get('screenshot_bytes')
    if not data:
        return
    target=next((sh for sh in slide.shapes if sh.shape_type==13 and sh.left<3000000 and sh.top>1800000),None)
    if not target:
        return
    left,top,width,height=target.left,target.top,target.width,target.height
    target.element.getparent().remove(target.element)
    with tempfile.NamedTemporaryFile(suffix='.png',delete=False) as f:
        f.write(data); path=f.name
    try:
        slide.shapes.add_picture(path,left,top,width=width,height=height)
    finally:
        os.remove(path)


def _rate(row,key):
    base=row.get('bc_visit',0)
    return row.get(key,0)/base*100 if base else None


def _fill_funnel(slide,p):
    name=p['product_name']; bcname=name
    h=_find_text(slide,lambda t,s:'BC Page 経路' in t)
    if h:
        _set_shape(h,f'{bcname} BC Page 経路',color=PALE,bold=True)
    title=_find_text(slide,lambda t,s:'購入経路' in t)
    if title:
        _set_shape(title,f'{name} BCからOrderまでの購入経路',color=BLACK,bold=True)
    b=_find_text(slide,lambda t,s:'CVR' in t)
    if b:
        styles=_text_frame_styles(b.text_frame)
        base_style=styles[0] if styles else None
        cur=p['funnel']['current']
        prev=p['funnel']['previous']
        lines=[]
        for seg,label in [('Organic Search','Organic'),('Paid','Paid')]:
            a=prev.get(seg,{})
            c=cur.get(seg,{})
            pc=(
                a.get('order',0)
                / a.get('bc_visit',1)
                * 100
            ) if a.get('bc_visit') else None
            cc=(
                c.get('order',0)
                / c.get('bc_visit',1)
                * 100
            ) if c.get('bc_visit') else None
            lines.append(
                f'{label} のBC VisitからOrderまでのCVRは '
                f'先週 {_pct(pc,2)} → 今週 {_pct(cc,2)}'
            )

        # Same treatment as page 1 / Explore:
        # keep template paragraph properties (bullet, indent, spacing)
        # and replace only the text.
        tf=b.text_frame
        tf.word_wrap=True
        tf.auto_size=MSO_AUTO_SIZE.NONE

        for index,line in enumerate(lines):
            paragraph=_ensure_styled_paragraph(
                tf,
                index,
            )
            style=(
                styles[index]
                if index<len(styles)
                else base_style
            )
            _set_paragraph_text_preserve_style(
                paragraph,
                line,
                style,
                color=BLACK,
                bold=False,
            )

        for paragraph in tf.paragraphs[len(lines):]:
            _set_paragraph_text_preserve_style(
                paragraph,
                '',
                base_style,
                color=BLACK,
                bold=False,
            )
    footer=_find_text(slide,lambda t,s:'Data：' in t)
    if footer:
        ds=p['date_start'].split('-'); de=p['date_end'].split('-')
        _set_shape(footer,f'Data：{int(ds[0])}/{int(ds[1])}/{int(ds[2])} ~ {int(de[1])}/{int(de[2])}',color=GREY,bold=False)
    t=_find_table(slide,19,11)
    if not t:
        raise RuntimeError('Funnel table not found')
    keys=['bc_visit','cart_add_event','add_on_visit','cart_page_visit','checkout_login','contact_info','delivery','payment',None,'order_confirmation','order']
    starts={'Organic Search':2,'Other':8,'Paid':14}
    for seg,sr in starts.items():
        c=p['funnel']['current'].get(seg,{})
        a=p['funnel']['previous'].get(seg,{})
        for ci,key in enumerate(keys):
            if key is None:
                for rr in (sr,sr+1,sr+3,sr+4):
                    _set_cell(t.cell(rr,ci),'',color=GREY,bold=False)
                continue
            value_color = WHITE if ci in (9,10) else (RBLUE if seg=='Paid' else GREY)
            _set_cell(
                t.cell(sr,ci),
                _num(c.get(key)) if c.get(key) else '',
                color=value_color,
                bold=True,
            )
            prev_abs = key in {'bc_visit','cart_add_event','cart_page_visit','order'}
            previous_color = WHITE if ci in (9,10) else GREY
            _set_cell(
                t.cell(sr+1,ci),
                f'(先週：{_num(a.get(key))})'
                if prev_abs and a.get(key)
                else '',
                color=previous_color,
                bold=True,
            )
            if key=='bc_visit':
                _set_cell(t.cell(sr+3,ci),'移動率',color=RBLUE if seg=='Paid' else GREY,bold=True)
                _set_cell(t.cell(sr+4,ci),'先週',color=RBLUE if seg=='Paid' else GREY,bold=True)
            else:
                rate_color = WHITE if ci in (9,10) else (RBLUE if seg=='Paid' else GREY)
                _set_cell(
                    t.cell(sr+3,ci),
                    _pct(_rate(c,key),1),
                    color=rate_color,
                    bold=True,
                )
                _set_cell(
                    t.cell(sr+4,ci),
                    _pct(_rate(a,key),1),
                    color=rate_color,
                    bold=True,
                )


def _no_autofit(slide):
    for sh in slide.shapes:
        if hasattr(sh,'text_frame') and sh.has_text_frame:
            sh.text_frame.auto_size=MSO_AUTO_SIZE.NONE


def _fill_summary(slide,p):
    _fill_title(slide,p)
    _fill_bullets(slide,p)
    _fill_summary_table(slide,p)
    _fill_carriers(slide,p)
    _fill_summary_meta(slide,p)
    _replace_screenshot(slide,p)
    _no_autofit(slide)


def build_pd_bc_report(products:list[dict[str,Any]])->bytes:
    prs=_load(); s1=prs.slides[0]; s2=prs.slides[1]
    for p in products:
        ns=_dup(prs,s1); _fill_summary(ns,p)
        if p.get('funnel',{}).get('current'):
            nf=_dup(prs,s2); _fill_funnel(nf,p); _no_autofit(nf)
    _remove_slide(prs,0); _remove_slide(prs,0)
    bio=io.BytesIO(); prs.save(bio); return bio.getvalue()
