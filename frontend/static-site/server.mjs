import {createServer} from "node:http";
import {readFile} from "node:fs/promises";
import {fileURLToPath} from "node:url";
import {join} from "node:path";

const root = fileURLToPath(new URL(".", import.meta.url));
const host = process.env.HOST || "0.0.0.0";
const port = Number(process.env.PORT || 3000);

const contentTypes = {
  ".b64": "text/plain; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".html": "text/html; charset=utf-8"
};

function contentType(pathname) {
  if (pathname.includes(".b64.")) return contentTypes[".b64"];
  if (pathname.endsWith(".json")) return contentTypes[".json"];
  return contentTypes[".html"];
}

createServer(async (request, response) => {
  const url = new URL(request.url || "/", `http://${request.headers.host}`);
  const pathname = url.pathname;
  let filename = "index.html";
  if (pathname === "/data.json") filename = "data.json";
  if (pathname.startsWith("/data.json.gz.b64.")) filename = pathname.slice(1);
  try {
    let body = await readFile(join(root, filename), "utf8");
    if (filename === "index.html" && !url.searchParams.has("noembed")) {
      const data = await readFile(join(root, "data.json"), "utf8");
      body = body.replace("<script>", `<script>window.__DASHBOARD_DATA__ = ${data.replaceAll("<", "\\u003c")};\n`);
    }
    response.writeHead(200, {
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-store",
      "Content-Type": contentType(filename)
    });
    response.end(request.method === "HEAD" ? undefined : body);
  } catch {
    response.writeHead(404, {"Content-Type": "text/plain; charset=utf-8"});
    response.end("Not found");
  }
}).listen(port, host, () => {
  console.log(`World Cup dashboard ready at http://${host}:${port}`);
});
