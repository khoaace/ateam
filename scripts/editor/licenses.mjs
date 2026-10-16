// Ghi giấy phép của các gói đã đóng vào codemirror.js (MIT) cạnh file build.
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
const out = [];
const walk = (dir) => {
  for (const name of readdirSync(dir).sort()) {
    if (name.startsWith(".")) continue;
    const p = join(dir, name);
    if (name.startsWith("@")) { walk(p); continue; }
    const pkg = join(p, "package.json");
    if (!existsSync(pkg)) continue;
    const meta = JSON.parse(readFileSync(pkg, "utf8"));
    if (meta.name === "esbuild" || meta.name.startsWith("@esbuild/")) continue;
    const lic = readdirSync(p).find((f) => /^licen[cs]e/i.test(f));
    out.push(`== ${meta.name}@${meta.version} (${meta.license || "?"})\n` + (lic ? readFileSync(join(p, lic), "utf8").trim() : ""));
  }
};
walk("node_modules");
writeFileSync("../../ateam/webui/vendor/LICENSES.txt", out.join("\n\n") + "\n");
console.log(`LICENSES.txt: ${out.length} gói`);
