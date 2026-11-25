// Makes the page's TypeScript types from the same JSON schemas the server
// checks against, so the page and the server can't drift apart.
//
// The schemas point to one another by file name. Here each schema, and each
// part inside it, gets a plain name, and is written out as a type. It reads
// only the few kinds of schema Shire uses, so it needs nothing installed.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const schemas = resolve(here, "../../src/shire/schemas");
const load = (name) => JSON.parse(readFileSync(resolve(schemas, `${name}.schema.json`), "utf8"));

// What each schema, and each part inside it, is called in TypeScript.
const NAMES = {
  status: { self: "Status", plugin: "Plugin", need: "Need" },
  output: { self: "Output", item: "Item" },
  settings: { self: "Settings", items: "Choices", choice: "Choice" },
  groups: { self: "Groups" },
};

const doc = (node, indent) => (node.description ? `${indent}/** ${node.description} */\n` : "");
const prop = (key) => (/^[A-Za-z_$][\w$]*$/.test(key) ? key : JSON.stringify(key));
const many = (type) => (type.includes(" | ") ? `(${type})[]` : `${type}[]`);

function ts(node, file, indent = "") {
  if (node.$ref) {
    const other = node.$ref.match(/^([a-z]+)\.schema\.json$/);
    const inside = node.$ref.match(/^#\/\$defs\/(.+)$/);
    const name = other ? NAMES[other[1]]?.self : inside ? NAMES[file][inside[1]] : null;
    if (!name) throw new Error(`${file}: ${node.$ref} has no name in NAMES`);
    return name;
  }
  if (node.enum) return node.enum.map((v) => JSON.stringify(v)).join(" | ");
  if (node.oneOf) return node.oneOf.map((n) => ts(n, file, indent)).join(" | ");
  const types = [].concat(node.type ?? []);
  if (types.length > 1) return types.map((type) => ts({ ...node, type }, file, indent)).join(" | ");
  switch (types[0]) {
    case "string": return "string";
    case "integer": case "number": return "number";
    case "boolean": return "boolean";
    case "null": return "null";
    case "array": return many(ts(node.items ?? {}, file, indent));
    case "object": {
      const inner = `${indent}  `;
      const required = new Set(node.required ?? []);
      const lines = Object.entries(node.properties ?? {}).map(
        ([key, value]) => `${doc(value, inner)}${inner}${prop(key)}${required.has(key) ? "" : "?"}: ${ts(value, file, inner)};`);
      if (node.additionalProperties && typeof node.additionalProperties === "object")
        lines.push(`${inner}[key: string]: ${ts(node.additionalProperties, file, inner)};`);
      return `{\n${lines.join("\n")}\n${indent}}`;
    }
    default: throw new Error(`${file}: a schema of a kind this script doesn't read: ${JSON.stringify(node).slice(0, 120)}`);
  }
}

let out = "// Made from src/shire/schemas by `npm run types`. Don't edit it by hand.\n";
for (const file of Object.keys(NAMES)) {
  const { $defs = {}, ...body } = load(file);
  for (const [name, node] of [[NAMES[file].self, body], ...Object.entries($defs).map(([k, v]) => [NAMES[file][k], v])]) {
    const plain = node.type === "object" && !node.enum;
    out += `\n${doc(node, "")}export ${plain ? `interface ${name} ` : `type ${name} = `}${ts(node, file)}${plain ? "" : ";"}\n`;
  }
}
writeFileSync(resolve(here, "../src/types.gen.ts"), out);
