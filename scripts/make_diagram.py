"""Render docs/img/how-it-works-{dark,light}.svg (stdlib only, deterministic).

    python scripts/make_diagram.py

The picture is a flow chart of what the library does, so it carries no data.
Only CSS-free SMIL is used (one moving dot), nothing needs script, and every
element is fully drawn in its base state. Text is plain font text.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MONO = 'ui-monospace,"SFMono-Regular","DM Mono","DejaVu Sans Mono",Menlo,Consolas,monospace'

DARK = dict(bg="#0d0e0c", win="#161715", line="#2a2c28", grid="#1a1b19", text="#F4F5F2",
            mute="#9a9c96", a="#00FF66", b="#B6FF2E")
LIGHT = dict(bg="#F4F5F2", win="#eceeea", line="#c4c7c0", grid="#e2e3df", text="#111211",
             mute="#54564f", a="#00A84A", b="#5f9a00")

W, H = 1200, 400
STEPS = [
    ("1  INPUTS", "spot, IV, rate,", "drift, DTE, seed"),
    ("2  SYNTHETIC PATH", "GBM stock path,", "mean-reverting IV"),
    ("3  PRICE THE LEGS", "Black-Scholes, or CRR", "tree for American"),
    ("4  TRADE P&amp;L", "open at entry DTE,", "close at exit DTE"),
    ("5  ATTRIBUTE", "delta gamma theta vega", "vanna volga + residual"),
]


def render(c):
    out = [f'<svg width="{W}" height="{H}" viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
           f'role="img" aria-labelledby="t d">',
           '<title id="t">How vanna works</title>',
           '<desc id="d">Five steps: inputs, a synthetic stock and implied-vol path, pricing each option leg '
           'with Black-Scholes or a binomial tree, trade profit and loss, then attribution of that P&amp;L to '
           'delta, gamma, theta, vega, vanna, volga and an explicit residual.</desc>',
           f'<defs><pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse">'
           f'<path d="M40 0H0V40" fill="none" stroke="{c["grid"]}"/></pattern>'
           f'<clipPath id="k"><rect width="{W}" height="{H}" rx="14"/></clipPath></defs>',
           '<g clip-path="url(#k)">',
           f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/><rect width="{W}" height="{H}" fill="url(#g)"/>',
           f'<rect width="{W}" height="40" fill="{c["win"]}"/><path d="M0 40H{W}" stroke="{c["line"]}"/>',
           '<circle cx="24" cy="20" r="6" fill="#ff5f57"/><circle cx="44" cy="20" r="6" fill="#febc2e"/>'
           '<circle cx="64" cy="20" r="6" fill="#28c840"/>',
           f'<text x="92" y="25" font-family=\'{MONO}\' font-size="13" fill="{c["mute"]}">vanna: how it works</text>',
           f'<text x="40" y="92" font-family=\'{MONO}\' font-size="13" letter-spacing="2.4" '
           f'fill="{c["a"]}">FROM INPUTS TO GREEK-ATTRIBUTED P&amp;L</text>']
    bw, gap = 196, 40
    for i, (head, l1, l2) in enumerate(STEPS):
        x = 40 + i * (bw + gap)
        hi = i == len(STEPS) - 1
        out.append(f'<rect x="{x}" y="128" width="{bw}" height="112" rx="10" fill="{c["win"]}" '
                   f'stroke="{c["a"] if hi else c["line"]}" stroke-width="{1.6 if hi else 1}"/>')
        out.append(f'<text x="{x+16}" y="160" font-family=\'{MONO}\' font-size="13" font-weight="700" '
                   f'fill="{c["text"]}">{head}</text>')
        out.append(f'<text x="{x+16}" y="192" font-family=\'{MONO}\' font-size="12" fill="{c["mute"]}">{l1}</text>')
        out.append(f'<text x="{x+16}" y="212" font-family=\'{MONO}\' font-size="12" fill="{c["mute"]}">{l2}</text>')
        if i < len(STEPS) - 1:
            ax = x + bw + 6
            out.append(f'<path d="M{ax} 184H{ax+26}" stroke="{c["mute"]}" stroke-width="1.6"/>'
                       f'<path d="M{ax+20} 178L{ax+26} 184L{ax+20} 190" fill="none" stroke="{c["mute"]}" '
                       f'stroke-width="1.6"/>')
    out.append(f'<text x="40" y="288" font-family=\'{MONO}\' font-size="12" fill="{c["b"]}">'
               'Whatever the Taylor terms do not explain is reported as "residual", never folded into a Greek.</text>')
    out.append(f'<text x="40" y="312" font-family=\'{MONO}\' font-size="12" fill="{c["mute"]}">'
               'Synthetic paths only: no market-data loader. Results are as realistic as the model, not more.</text>')
    out.append(f'<circle cx="60" cy="116" r="4.5" fill="{c["b"]}">'
               '<animate attributeName="cx" values="60;1140" dur="7s" repeatCount="indefinite"/></circle>')
    out.append('<style>@media (prefers-reduced-motion:reduce){*{animation:none!important}}</style>')
    out.append(f'</g><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="14" fill="none" stroke="{c["line"]}"/></svg>')
    return "\n".join(out) + "\n"


(ROOT / "docs/img/how-it-works-dark.svg").write_text(render(DARK))
(ROOT / "docs/img/how-it-works-light.svg").write_text(render(LIGHT))
