"""The guide's Latin font: DotGothic16 (OFL) with each letter only as wide as its dots, like a game's VWF.

  uv run --with fonttools --with brotli python tools/make_font.py DotGothic16-Regular.ttf station/static/dot.woff2

DotGothic16-Regular.ttf is from github.com/google/fonts (ofl/dotgothic16). Japanese still comes from DotGothic16 itself.
"""
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem

NAME = 'Station Dot'
DOT = 125       # one dot of the 16x16 grid at 2000 units per em
SPACE = 5


def main(src: str, out: str) -> None:
    font = TTFont(src, recalcTimestamp=False)
    options = subset.Options()
    options.layout_features = []
    options.name_IDs = [0, 13, 14]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[*range(0x20, 0x7f), 0xb7])
    subsetter.subset(font)
    # whole dots are then whole units, so moving a glyph by dots never blurs it
    scale_upem(font, 2000)

    glyf, hmtx, cmap = font['glyf'], font['hmtx'], font.getBestCmap()
    digits = {cmap[c] for c in range(0x30, 0x3a)}
    for name in font.getGlyphOrder():
        glyph = glyf[name]
        if not glyph.numberOfContours:
            continue
        glyph.recalcBounds(glyf)
        # the outlines sit half a dot off the pixel grid at 16px; the extra half dot puts each stroke on one pixel
        first, last = round((glyph.xMin + DOT // 2) / DOT), round((glyph.xMax + DOT // 2) / DOT)
        if name in digits:
            first, last = 1, 8    # digits keep one width so the clock doesn't wobble
        glyph.coordinates.translate((DOT // 2 - first * DOT, 0))
        glyph.recalcBounds(glyf)
        hmtx[name] = ((last - first + 1) * DOT, glyph.xMin)
    hmtx[cmap[0x20]] = (SPACE * DOT, 0)
    font['hhea'].advanceWidthMax = max(width for width, _ in hmtx.metrics.values())

    font['name'].setName(NAME, 1, 3, 1, 0x409)
    font['name'].setName('Regular', 2, 3, 1, 0x409)
    font['name'].setName(NAME, 4, 3, 1, 0x409)
    font['name'].setName(NAME.replace(' ', '') + '-Regular', 6, 3, 1, 0x409)
    font.flavor = 'woff2'
    font.save(out)


if __name__ == '__main__':
    main(*sys.argv[1:3])
