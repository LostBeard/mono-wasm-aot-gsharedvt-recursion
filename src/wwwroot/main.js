import { dotnet } from './_framework/dotnet.js';

// Console.WriteLine in browser-wasm goes to console.log: mirror it into the page.
const out = document.getElementById('out');
const lines = [];
const show = () => { out.textContent = lines.join('\n'); };
for (const level of ['log', 'info', 'warn', 'error']) {
    const original = console[level].bind(console);
    console[level] = (...args) => {
        original(...args);
        lines.push((level === 'error' ? 'ERR: ' : '') + args.join(' '));
        show();
    };
}

try {
    const { runMain } = await dotnet.create();
    const code = await runMain();
    lines.push('exit code ' + code);
} catch (e) {
    lines.push('FAILED: ' + e);
}
show();
