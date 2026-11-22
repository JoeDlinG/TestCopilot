// Verify the production chunk graph has no 2-cycles between vendor chunks.
// The 2026-10-24 white-screen incident: @ant-design/icons read
// @ant-design/colors at module top level while antd imported icons — two
// chunks importing each other meant one side evaluated as undefined.
import fs from 'fs';
import path from 'path';

const dir = path.resolve('dist/assets');
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.js'));
const imports = new Map();

for (const f of files) {
  const src = fs.readFileSync(path.join(dir, f), 'utf8');
  const set = new Set();
  const re = /from\s*"(\.\/[^"]+)"/g;
  let m;
  while ((m = re.exec(src))) {
    const target = m[1].replace('./', '').replace(/\.js$/, '');
    set.add(target);
  }
  imports.set(f.replace(/\.js$/, ''), set);
}

const cycles = [];
for (const [a, deps] of imports) {
  for (const b of deps) {
    if (imports.has(b) && imports.get(b).has(a) && a < b) {
      cycles.push(`${a} <-> ${b}`);
    }
  }
}

console.log(`chunks: ${files.length}`);
console.log(cycles.length ? `2-CYCLES FOUND:\n${cycles.join('\n')}` : 'no 2-cycles');
process.exit(cycles.length ? 1 : 0);
