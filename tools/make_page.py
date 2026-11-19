"""Build the GitHub Pages index from the per-job result JSON files.
Usage: python make_page.py <results dir> <site dir> <run url>"""
import glob
import html
import json
import os
import sys

results_dir, site, run_url = sys.argv[1:4]
rows = []
for f in sorted(glob.glob(os.path.join(results_dir, '**', 'result-*.json'), recursive=True)):
    rows.append(json.load(open(f)))
order = {'net9.0': 0, 'net10.0': 1, 'net11.0': 2}
rows.sort(key=lambda r: (order.get(r['framework'], 9), r['arm']))


def fmt(v, unit='s'):
    if v is None:
        return 'n/a'
    if unit == 's' and v >= 120:
        return f'{v:,.0f} s ({v / 60:.1f} min)'
    return f'{v:,.1f} {unit}' if isinstance(v, float) else f'{v:,} {unit}'.strip()


body = []
for r in rows:
    app = f"apps/{r['framework']}-{r['arm']}/"
    per = None
    if r.get('aot_instances_emit_jit_s') is not None and r.get('aot_instances_methods'):
        per = r['aot_instances_emit_jit_s'] * 1000 / r['aot_instances_methods']
    other_per = None
    if r.get('other_passes_methods'):
        other_per = r['other_passes_jit_s'] * 1000 / r['other_passes_methods']
    body.append('<tr>' + ''.join(f'<td>{c}</td>' for c in [
        html.escape(r['framework']),
        'ON (polymorphic recursion)' if r['arm'] == 'on' else 'OFF (non-generic path)',
        fmt(float(r['publish_wall_s'])),
        fmt(r.get('aot_instances_emit_jit_s')),
        fmt(r.get('aot_instances_methods'), ''),
        fmt(per, 'ms') if per is not None else 'n/a',
        fmt(other_per, 'ms') if other_per is not None else 'n/a',
        f'<a href="{app}">run</a>',
    ]) + '</tr>')

page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mono AOT gsharedvt recursion</title>
<style>
:root {{ --bg:#fff; --fg:#111; --muted:#555; --line:#ddd; --head:#f3f3f3; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#111; --fg:#eee; --muted:#aaa; --line:#333; --head:#1c1c1c; }} }}
body {{ background:var(--bg); color:var(--fg); font-family:system-ui,sans-serif; margin:16px; max-width:1100px; }}
.wrap {{ overflow-x:auto; }} table {{ border-collapse:collapse; width:100%; }}
th,td {{ border:1px solid var(--line); padding:6px 8px; text-align:left; white-space:nowrap; }} th {{ background:var(--head); }}
p {{ color:var(--muted); line-height:1.5; }} a {{ color:inherit; }}
</style></head><body>
<h1>Browser-wasm AOT: polymorphic recursion over struct type arguments</h1>
<p>Same tiny console app, built twice per framework. ON: a generic method recurses into itself with its struct
type arguments wrapped one level deeper (the shape of ILGPU's ArgumentMapper). OFF: the same walk with a non-generic
field path. Columns come from mono-aot-cross's own "Compiled" and "JIT time" lines in the publish log
(WasmDedup default, so generic instances compile in the aot-instances.dll pass). Measured by this repo's
GitHub Actions run: <a href="{html.escape(run_url)}">{html.escape(run_url)}</a></p>
<div class="wrap"><table>
<tr><th>Framework</th><th>Arm</th><th>Publish wall time</th><th>aot-instances JIT (emit phase)</th><th>Instances</th>
<th>ms per instance</th><th>ms per method, other passes</th><th>App</th></tr>
{"".join(body)}
</table></div>
<p>The aot-instances pass also runs a collect phase before the emit phase (it re-compiles every input assembly
to find shareable instances); mono prints no timing for it, so it shows only in the publish wall time.
Each app prints its mapping result in the page; both arms must print <code>ops 3 / 3</code> and exit 0.</p>
</body></html>'''
os.makedirs(site, exist_ok=True)
open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(page)
print(f'{len(rows)} rows')
