"""Pull AOT timing out of a diagnostic MSBuild log replayed from the publish binlog:
    dotnet msbuild pub.binlog -noconlog "-flp:logfile=diag.log;verbosity=diagnostic;performancesummary"
Usage: python extract.py <diag.log> <framework> <arm> <wallSeconds> <out.json>

Sources, in the log:
- MSBuild's Task Performance Summary: total time of the MonoAOTCompiler task (every mono-aot-cross pass, including the
  single-threaded aot-instances.dll dedup pass) and of EmccCompile (bitcode -> object).
- MonoAOTCompiler's per-pass output after '[<assembly>] Exec (with response file contents expanded)':
  'Adding N dedup-ed methods.' and 'Compiled: N/M', plus 'JIT time: X ms, Generation time: Y ms' where mono prints it
  (the Windows cross compiler does; the Linux one in this log does not)."""
import json
import re
import sys

log, fw, arm, wall, out = sys.argv[1:6]
lines = open(log, encoding='utf-8', errors='replace').read().splitlines()

passes = {}
last = None
for line in lines:
    m = re.search(r'\[([^\]]+\.dll)\] Exec \(with response', line)
    if m:
        last = m.group(1)
        passes.setdefault(last, {})
        continue
    if last is None:
        continue
    m = re.search(r'Adding (\d+) dedup-ed methods', line)
    if m:
        passes[last]['dedup_methods'] = int(m.group(1))
    m = re.search(r'Compiled: (\d+)/(\d+)', line)
    if m and 'compiled' not in passes[last]:
        passes[last]['compiled'] = int(m.group(1))
        passes[last]['methods'] = int(m.group(2))
    m = re.search(r'JIT time: (\d+) ms, Generation time: (\d+) ms', line)
    if m and 'jit_ms' not in passes[last]:
        passes[last]['jit_ms'] = int(m.group(1))
        passes[last]['gen_ms'] = int(m.group(2))

tasks = {}
in_summary = False
for line in lines:
    if 'Task Performance Summary' in line:
        in_summary = True
        continue
    if in_summary:
        m = re.match(r'\s+(\d+) ms\s+(\S+)\s+(\d+) calls', line)
        if m:
            tasks[m.group(2)] = tasks.get(m.group(2), 0) + int(m.group(1))
        elif line.strip() and not line.startswith(' '):
            in_summary = False

inst = passes.get('aot-instances.dll', {})
others = {k: v for k, v in passes.items() if k != 'aot-instances.dll'}
res = {
    'framework': fw,
    'arm': arm,
    'publish_wall_s': int(wall),
    'mono_aot_task_s': tasks['MonoAOTCompiler'] / 1000 if 'MonoAOTCompiler' in tasks else None,
    'emcc_compile_task_s': tasks['EmccCompile'] / 1000 if 'EmccCompile' in tasks else None,
    'aot_instances_dedup_methods': inst.get('dedup_methods'),
    'aot_instances_compiled': inst.get('compiled'),
    'aot_instances_emit_jit_s': inst['jit_ms'] / 1000 if 'jit_ms' in inst else None,
    'other_passes_compiled': sum(v.get('compiled', 0) for v in others.values()),
    'other_passes_jit_s': (sum(v['jit_ms'] for v in others.values() if 'jit_ms' in v) / 1000
                           if any('jit_ms' in v for v in others.values()) else None),
    'passes': passes,
}
json.dump(res, open(out, 'w'), indent=2)
print(json.dumps({k: v for k, v in res.items() if k != 'passes'}, indent=2))
