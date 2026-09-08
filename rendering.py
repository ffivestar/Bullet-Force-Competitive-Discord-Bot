"""Deterministic bracket PNGs rendered from the stored match graph."""
from __future__ import annotations

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


def font(size):
    for path in ('/System/Library/Fonts/Supplemental/Arial.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def bracket_png(t):
    columns = {}
    for m in t['matches'].values():
        columns.setdefault((m['bracket'], m['round']), []).append(m)
    groups = {b: sorted([key for key in columns if key[0] == b]) for b in ('W', 'L', 'G')}
    max_cols = max((len(v) for v in groups.values()), default=1)
    width = max(1000, 60 + max_cols*300)
    heights = {b: max(1, max((len(columns[key]) for key in groups[b]), default=1))*104+70 for b in groups}
    height = 125+sum(heights.values())+60
    im = Image.new('RGB', (width, height), '#10141b')
    d = ImageDraw.Draw(im)
    title, body, small = font(28), font(16), font(12)

    def fit(text, max_width, face):
        text = str(text)
        while text and d.textlength(text, font=face) > max_width:
            text = text[:-2] + '…' if len(text) > 2 else ''
        return text

    d.text((30, 20), fit('BFC  /  '+t['name'], width-60, title), font=title, fill='#f1f5f9')
    subtitle = f"Tournament #{t['id']}  •  {len(t['teams'])} teams  •  Double elimination  •  {t['status'].upper()}"
    d.text((30, 61), subtitle, font=body, fill='#99a8bc')
    if t.get('champion'):
        d.text((30, 88), 'CHAMPION: '+t['teams'][t['champion']]['name'], font=body, fill='#f2ca6b')
    positions = {}
    top = 125
    for b, label in [('W', 'WINNERS BRACKET'), ('L', 'LOSERS BRACKET'), ('G', 'GRAND FINAL')]:
        d.text((30, top), label, font=body, fill='#f2ca6b' if b=='G' else '#59cbbb')
        for col, key in enumerate(groups[b]):
            matches = columns[key]
            area = heights[b]-70
            for i, m in enumerate(matches):
                x = 30+col*300
                y = top+40+int((i+0.5)*area/len(matches))-43
                positions[m['id']] = (x, y)
        top += heights[b]
    # Within-bracket connectors. Cross-bracket drops are explicitly labelled on slots.
    for m in t['matches'].values():
        x, y = positions[m['id']]
        for slot, (kind, source) in enumerate(m['sources']):
            if kind != 'seed' and source in positions and t['matches'][source]['bracket'] == m['bracket']:
                sx, sy = positions[source]
                d.line([(sx+268, sy+44), (x-16, sy+44), (x-16, y+38+slot*24), (x, y+38+slot*24)], fill='#42536a', width=2)
    for m in t['matches'].values():
        x, y = positions[m['id']]
        color = '#325b55' if m['status']=='complete' else '#354153'
        d.rounded_rectangle((x,y,x+268,y+87), radius=6, fill='#1d2633', outline=color, width=2)
        d.text((x+10,y+5), f"{m['id']}  ·  Round {m['round']}  ·  {m['status']}",font=small,fill='#99a8bc')
        for i, tid in enumerate(m['teams']):
            kind, source = m['sources'][i]
            name = t['teams'][tid]['name'] if tid else ('BYE' if m['status']=='bye' or kind=='seed' else f'{kind.title()} {source}')
            d.text((x+10,y+28+i*25),fit(name,214,body),font=body,fill='#f2ca6b' if tid and tid==m['winner'] else '#eef2f7')
            if m['result']:
                d.text((x+235,y+28+i*25),str(m['result']['scores'][i]),font=body,fill='#eef2f7')
    d.text((30,height-35),'One loss → losers bracket  •  Two losses → eliminated  •  Grand final reset: '+('ON' if t['grand_final_reset'] else 'OFF'),font=small,fill='#99a8bc')
    out = BytesIO()
    im.save(out, format='PNG')
    out.seek(0)
    return out
