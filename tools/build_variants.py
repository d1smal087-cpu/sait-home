"""Generate portable design variants using only the Python standard library."""
from base64 import b64encode
from pathlib import Path

root = Path(__file__).resolve().parents[1]
page = (root / 'index.html').read_text(encoding='utf-8')
for name in ('style.css', 'themes.css'):
    css = (root / name).read_text(encoding='utf-8')
    page = page.replace(f'<link rel="stylesheet" href="{name}">', f'<style>\n{css}\n</style>')
script = (root / 'script.js').read_text(encoding='utf-8')
page = page.replace('<script src="script.js" defer></script>', '')
page = page.replace('</body>', f'<script>\n{script}\n</script>\n</body>')
for name in ('mark.svg', 'staircase.svg'):
    encoded = b64encode((root / 'assets' / name).read_bytes()).decode('ascii')
    page = page.replace(f'assets/{name}', f'data:image/svg+xml;base64,{encoded}')
variants = [
    ('dark', 'variant-graphite.html', '#191c1e'),
    ('light', 'variant-blue.html', '#ffffff'),
    ('emerald', 'variant-emerald.html', '#123b35'),
    ('sand', 'variant-sand.html', '#f5eddd'),
]
for theme, filename, color in variants:
    output = page.replace('data-theme="warm"', f'data-theme="{theme}"', 1)
    output = output.replace('content="#eee9df"', f'content="{color}"', 1)
    (root / filename).write_text(output, encoding='utf-8')
    print(filename)
