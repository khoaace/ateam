// Gói CodeMirror 6 cho tab Code của `ateam web` — mọi thứ trang cần nằm trong window.CM (xem ateam/webui/app.js).
import { basicSetup } from "codemirror";
import { EditorState, Compartment } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { indentWithTab } from "@codemirror/commands";
import { StreamLanguage } from "@codemirror/language";
import { oneDark } from "@codemirror/theme-one-dark";
import { vim, Vim, getCM } from "@replit/codemirror-vim";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { json } from "@codemirror/lang-json";
import { markdown } from "@codemirror/lang-markdown";
import { rust } from "@codemirror/lang-rust";
import { go } from "@codemirror/lang-go";
import { java } from "@codemirror/lang-java";
import { cpp } from "@codemirror/lang-cpp";
import { php } from "@codemirror/lang-php";
import { sql } from "@codemirror/lang-sql";
import { xml } from "@codemirror/lang-xml";
import { yaml } from "@codemirror/lang-yaml";
import { shell } from "@codemirror/legacy-modes/mode/shell";
import { toml } from "@codemirror/legacy-modes/mode/toml";
import { dockerFile } from "@codemirror/legacy-modes/mode/dockerfile";
import { ruby } from "@codemirror/legacy-modes/mode/ruby";
import { swift } from "@codemirror/legacy-modes/mode/swift";
import { kotlin } from "@codemirror/legacy-modes/mode/clike";
import { lua } from "@codemirror/legacy-modes/mode/lua";
import { properties } from "@codemirror/legacy-modes/mode/properties";

const legacy = (m) => () => StreamLanguage.define(m);
// [tên, đuôi file / tên file, hàm tạo] — đủ cho phần lớn dự án; file khác mở dạng chữ thường
const LANGS = [
  ["TypeScript JSX", /\.tsx$/i, () => javascript({ jsx: true, typescript: true })],
  ["TypeScript", /\.(ts|mts|cts)$/i, () => javascript({ typescript: true })],
  ["JavaScript JSX", /\.jsx$/i, () => javascript({ jsx: true })],
  ["JavaScript", /\.(js|mjs|cjs)$/i, () => javascript()],
  ["Python", /\.(py|pyi|pyw)$/i, () => python()],
  ["HTML", /\.(html?|vue|svelte|jinja2?|j2)$/i, () => html()],
  ["CSS", /\.(css|scss|less)$/i, () => css()],
  ["JSON", /\.(json|jsonc|json5)$|^\.?(babelrc|eslintrc|prettierrc)$/i, () => json()],
  ["Markdown", /\.(md|markdown|mdx)$/i, () => markdown()],
  ["Rust", /\.rs$/i, () => rust()],
  ["Go", /\.go$/i, () => go()],
  ["Java", /\.java$/i, () => java()],
  ["Kotlin", /\.kts?$/i, legacy(kotlin)],
  ["C/C++", /\.(c|h|cc|cpp|cxx|hpp|hh|hxx|m|mm)$/i, () => cpp()],
  ["PHP", /\.php$/i, () => php()],
  ["SQL", /\.sql$/i, () => sql()],
  ["XML", /\.(xml|svg|plist|xsd|xsl)$/i, () => xml()],
  ["YAML", /\.(ya?ml)$/i, () => yaml()],
  ["TOML", /\.toml$|^(Pipfile|poetry\.lock|Cargo\.lock)$/i, legacy(toml)],
  ["Shell", /\.(sh|bash|zsh|fish|command)$|^(\.?(bash|zsh)rc|\.?profile|\.env.*)$/i, legacy(shell)],
  ["Dockerfile", /^(Dockerfile|Containerfile)(\..*)?$|\.dockerfile$/i, legacy(dockerFile)],
  ["Ruby", /\.(rb|rake|gemspec)$|^(Gemfile|Rakefile)$/i, legacy(ruby)],
  ["Swift", /\.swift$/i, legacy(swift)],
  ["Lua", /\.lua$/i, legacy(lua)],
  ["Properties", /\.(ini|cfg|conf|properties)$|^\.(editorconfig|gitconfig)$/i, legacy(properties)],
];

window.CM = {
  basicSetup, EditorState, Compartment, EditorView, keymap, indentWithTab, oneDark, vim, Vim, getCM,
  languageFor(filename) {
    const base = filename.split("/").pop();
    const hit = LANGS.find(([, re]) => re.test(base));
    return hit ? { name: hit[0], support: hit[2]() } : null;
  },
};
