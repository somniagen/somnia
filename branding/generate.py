# regenerates branding/svg: .venv/Scripts/python branding/generate.py branding/svg (pngs were rendered from these with resvg)
import os
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

OUT = sys.argv[1]
FONTS = 'web/node_modules/@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-{}-normal.woff'
INK = '#161616'
PAPER = '#f2f2f2'

# crescent = circle(14.5, 17.5, 9.5) minus circle(19.5, 12.5, 9.5), plus the four point sparkle
CRESCENT = 'M10.765 8.765A9.5 9.5 0 1 0 23.235 21.235A9.5 9.5 0 0 1 10.765 8.765Z'
SPARKLE = 'M23 5.5l1.1 2.9 2.9 1.1-2.9 1.1L23 13.5l-1.1-2.9-2.9-1.1 2.9-1.1z'


def text_paths(text, weight, size, track_em=0.0):
    f = TTFont(FONTS.format(weight))
    gs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f['hmtx']
    upm = f['head'].unitsPerEm
    s = size / upm
    x = 0.0
    out = []
    for ch in text:
        g = cmap[ord(ch)]
        if ch != ' ':
            pen = SVGPathPen(gs)
            gs[g].draw(pen)
            out.append(f'<path transform="translate({x * s:.3f} 0) scale({s:.5f} {-s:.5f})" d="{pen.getCommands()}"/>')
        x += hmtx[g][0] + track_em * upm
    x -= track_em * upm
    cap = f['OS/2'].sCapHeight * s
    return '\n    '.join(out), x * s, cap


def mark(fill):
    return f'<g fill="{fill}"><path d="{CRESCENT}"/><path d="{SPARKLE}"/></g>'


def svg(vb, body, w=None, h=None):
    size = f' width="{w}" height="{h}"' if w else ''
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}"{size}>\n  {body}\n</svg>\n'


def write(name, content):
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        f.write(content)


os.makedirs(OUT, exist_ok=True)

# icon: the mark alone on transparent
for tone, fill in (('positive', INK), ('negative', PAPER)):
    write(f'somnia-icon-{tone}.svg', svg('3 3.25 26 26', mark(fill)))

# app icon tiles with their own background
tiles = {
    'negative': ('#1d1d1d', '#0b0b0b', PAPER, 'rgb(255 255 255 / 0.1)'),
    'positive': ('#ffffff', '#e4e4e4', INK, 'rgb(0 0 0 / 0.06)'),
}
for tone, (top, bottom, fill, edge) in tiles.items():
    body = f'''<defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{top}"/>
      <stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
  </defs>
  <rect width="32" height="32" rx="7" fill="url(#bg)"/>
  <rect x="0.25" y="0.25" width="31.5" height="31.5" rx="6.75" fill="none" stroke="{edge}" stroke-width="0.5"/>
  <g transform="translate(16 16.25) scale(0.78) translate(-16 -16.25)">{mark(fill)}</g>'''
    write(f'somnia-icon-tile-{tone}.svg', svg('0 0 32 32', body))

# horizontal logo: mark + wordmark (plex sans 600, tracked like the app)
paths, width, cap = text_paths('Somnia', 600, 19.84, 0.06)
base = 16.25 + cap / 2
tx = 31.5
for tone, fill in (('positive', INK), ('negative', PAPER)):
    body = f'''{mark(fill)}
  <g fill="{fill}" transform="translate({tx} {base:.3f})">
    {paths}
  </g>'''
    write(f'somnia-logo-{tone}.svg', svg(f'3 3.25 {tx + width - 1:.2f} 26', body))

# stacked logo for square placements
paths_s, width_s, cap_s = text_paths('Somnia', 600, 11, 0.06)
for tone, fill in (('positive', INK), ('negative', PAPER)):
    body = f'''<g transform="translate({(width_s + 4) / 2 - 16:.3f} 0)">{mark(fill)}</g>
  <g fill="{fill}" transform="translate(2 {28.25 + 4 + cap_s:.3f})">
    {paths_s}
  </g>'''
    write(f'somnia-logo-stacked-{tone}.svg', svg(f'0 3.25 {width_s + 4:.2f} {30 + cap_s + 2:.2f}', body))

# social / og card, 1200x630, in the app's dark gradient look
big, bw, bcap = text_paths('Somnia', 600, 96, 0.06)
tag, tw, tcap = text_paths('Local image generation for Illustrious and Anima', 400, 30)
m = 4.6
lw = 24 * m + 24 + bw
lx = (1200 - lw) / 2
cy = 270
card = f'''<defs>
    <radialGradient id="top" cx="0.5" cy="-0.15" r="0.9">
      <stop offset="0" stop-color="#262626"/>
      <stop offset="1" stop-color="#262626" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#131313"/>
      <stop offset="1" stop-color="#0a0a0a"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0.16"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect width="1200" height="630" fill="url(#top)"/>
  <ellipse cx="{lx + 12 * m:.1f}" cy="{cy}" rx="230" ry="230" fill="url(#glow)"/>
  <g transform="translate({lx:.2f} {cy - 12 * m:.2f}) scale({m}) translate(-4 -4.25)">{mark(PAPER)}</g>
  <g fill="{PAPER}" transform="translate({lx + 24 * m + 24:.2f} {cy + bcap / 2:.2f})">
    {big}
  </g>
  <g fill="#9a9a9a" transform="translate({(1200 - tw) / 2:.2f} {cy + 150:.2f})">
    {tag}
  </g>'''
write('somnia-social-card.svg', svg('0 0 1200 630', card, 1200, 630))
print('ok')
