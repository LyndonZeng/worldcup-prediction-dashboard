import { readFileSync, writeFileSync } from "node:fs";
import { gzipSync } from "node:zlib";

const input = new URL("../frontend/static-site/data.json", import.meta.url);
const outputBase = new URL("../frontend/static-site/data.json.gz.b64.", import.meta.url);
const chunks = 8;
const encoded = gzipSync(readFileSync(input), { level: 9, mtime: 0 }).toString("base64");
const chunkSize = Math.ceil(encoded.length / chunks);

for (let index = 0; index < chunks; index += 1) {
  const value = encoded.slice(index * chunkSize, (index + 1) * chunkSize);
  writeFileSync(new URL(`${outputBase.href}${index}`), value, "ascii");
}

console.log(`Built ${chunks} chunks from ${encoded.length} base64 characters.`);
