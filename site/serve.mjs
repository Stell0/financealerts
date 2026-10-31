// Preview under the same project subpath as GitHub Pages; no production server.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("./public/", import.meta.url));
const types = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
};
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, "http://localhost");
    if (!url.pathname.startsWith("/financealerts/")) {
      res.writeHead(302, { Location: "/financealerts/" });
      res.end();
      return;
    }
    const relative =
      decodeURIComponent(url.pathname.slice("/financealerts/".length)) ||
      "index.html";
    const filename = path.resolve(root, relative);
    if (!filename.startsWith(root)) {
      res.writeHead(403);
      res.end();
      return;
    }
    const content = await readFile(filename);
    res.writeHead(200, {
      "Content-Type":
        types[path.extname(filename)] || "application/octet-stream",
      "Cache-Control": "no-store",
    });
    res.end(content);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
});
server.listen(4173, "127.0.0.1", () =>
  console.log("Dashboard preview: http://127.0.0.1:4173/financealerts/"),
);
process.on("SIGTERM", () => server.close());
