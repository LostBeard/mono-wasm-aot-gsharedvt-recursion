"""Pull mono's own AOT timing for every pass out of a diagnostic MSBuild log (replayed from the publish binlog).
Usage: python extract.py <diag.log> <framework> <arm> <wallSeconds> <out.json>
Each mono-aot-cross pass prints 'Compiled: N/M' and 'JIT time: X ms, Generation time: Y ms'; MonoAOTCompiler logs that
output after the '[<assembly>] Exec (with response file contents expanded)' line. The bitcode compile prints
'[i/n] <file>.bc -> <file>.o [took Xs]'."""
import json
import re
import sys

log, fw, arm, wall, out = sys.argv[1:6]
lines = open(log, encoding='utf-8', errors='replace').read().splitlines()
passes = []
last = None
compiled = None
bc_took = {}
for line in lines:
    m = re.search(r'\[([^\]]+\.dll)\] Exec \(with response', line)
    if m:
        last = m.group(1)
    m = re.search(r'Compiled: (\d+)/(\d+)', line)
    if m:
        compiled = (int(m.group(1)), int(m.group(2)))
    m = re.search(r'JIT time: (\d+) ms, Generation time: (\d+) ms', line)
    if m:
        passes.append({'assembly': last, 'jit_ms': int(m.group(1)), 'gen_ms': int(m.group(2)),
                       'compiled': compiled[0] if compiled else None, 'methods': compiled[1] if compiled else None})
    m = re.search(r'\] (\S+?)\.bc -> \S+\.o \[took ([\d.]+)s\]', line)
    if m:
        bc_took[m.group(1)] = float(m.group(2))

inst = next((p for p in passes if p['assembly'] == 'aot-instances.dll'), None)
others = [p for p in passes if p['assembly'] != 'aot-instances.dll']
res = {
    'framework': fw, 'arm': arm, 'publish_wall_s': int(wall),
    'aot_instances_emit_jit_s': inst['jit_ms'] / 1000 if inst else None,
    'aot_instances_emit_gen_s': inst['gen_ms'] / 1000 if inst else None,
    'aot_instances_methods': inst['compiled'] if inst else None,
    'other_passes_jit_s': sum(p['jit_ms'] for p in others) / 1000,
    'other_passes_methods': sum((p['compiled'] or 0) for p in others),
    'aot_instances_bc_to_o_s': bc_took.get('aot-instances.dll'),
    'passes': passes,
}
json.dump(res, open(out, 'w'), indent=2)
print(json.dumps({k: v for k, v in res.items() if k != 'passes'}, indent=2))
