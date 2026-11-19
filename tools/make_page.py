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
    body.append('<tr>' + ''.join(f'<td>{c}</td>' for c in [
        html.escape(r['framework']),
        'ON (polymorphic recursion)' if r['arm'] == 'on' else 'OFF (non-generic path)',
        fmt(float(r['publish_wall_s'])),
        fmt(r.get('mono_aot_task_s')),
        fmt(r.get('aot_instances_compiled'), ''),
        fmt(r.get('aot_instances_emit_jit_s')),
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
field path. Times come from MSBuild's task performance summary of the publish binlog (MonoAOTCompiler = every
mono-aot-cross pass, including the single-threaded aot-instances.dll dedup pass) and mono's own "Compiled" lines.
Measured by this repo's
GitHub Actions run: <a href="{html.escape(run_url)}">{html.escape(run_url)}</a></p>
<div class="wrap"><table>
<tr><th>Framework</th><th>Arm</th><th>Publish wall time</th><th>MonoAOTCompiler task (all AOT passes)</th>
<th>aot-instances compiled</th><th>aot-instances emit JIT (Windows mono only)</th><th>App</th></tr>
{"".join(body)}
</table></div>
<p>The aot-instances pass runs a collect phase before its emit phase (it re-compiles every input assembly to find
shareable instances); mono prints no timing for that phase, but it is inside the MonoAOTCompiler task time.
Each app prints its mapping result in the page; both arms must print <code>ops 3 / 3</code> and exit 0.</p>
</body></html>'''
os.makedirs(site, exist_ok=True)
open(os.path.join(site, 'index.html'), 'w', encoding='utf-8').write(page)
print(f'{len(rows)} rows')
