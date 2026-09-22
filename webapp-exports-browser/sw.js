// Serves files straight out of the directory picked in index.html, under a
// virtual "__mm_preview__/…" URL, so exported channel pages load with real
// relative image paths instead of rewritten ones. Requires https:// or
// localhost — index.html falls back to base64 rewriting on file://.

const PREVIEW_PREFIX = "__mm_preview__/";
const DB_NAME = "mm-archive-browser";
const STORE_NAME = "handles";
const HANDLE_KEY = "root";

const MIME_TYPES = {
  html: "text/html",
  htm: "text/html",
  svg: "image/svg+xml",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  bmp: "image/bmp",
  ico: "image/x-icon",
  pdf: "application/pdf",
  json: "application/json",
  txt: "text/plain",
  css: "text/css",
  js: "text/javascript",
};

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

function openHandleDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE_NAME);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function getRootHandle() {
  const db = await openHandleDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).get(HANDLE_KEY);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

function guessMimeType(name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  return MIME_TYPES[ext] || "application/octet-stream";
}

async function resolveFile(rootHandle, segments) {
  let dirHandle = rootHandle;
  for (let i = 0; i < segments.length - 1; i++) {
    dirHandle = await dirHandle.getDirectoryHandle(segments[i]);
  }
  const fileHandle = await dirHandle.getFileHandle(segments[segments.length - 1]);
  return fileHandle.getFile();
}

async function handlePreviewRequest(url) {
  const markerIndex = url.pathname.indexOf(PREVIEW_PREFIX);
  const path = decodeURIComponent(url.pathname.slice(markerIndex + PREVIEW_PREFIX.length));
  const segments = path.split("/").filter(Boolean);
  if (segments.length === 0) {
    return new Response("Not found", { status: 404 });
  }

  let rootHandle;
  try {
    rootHandle = await getRootHandle();
  } catch (e) {
    return new Response("No directory handle available", { status: 404 });
  }
  if (!rootHandle) {
    return new Response("No directory selected yet", { status: 404 });
  }

  try {
    const perm = await rootHandle.queryPermission({ mode: "read" });
    if (perm !== "granted") {
      return new Response("Permission not granted for this directory", { status: 403 });
    }
  } catch (e) {
    return new Response("Permission check failed", { status: 403 });
  }

  try {
    const file = await resolveFile(rootHandle, segments);
    const type = file.type || guessMimeType(file.name);
    return new Response(file, { status: 200, headers: { "Content-Type": type } });
  } catch (e) {
    return new Response("File not found: " + path, { status: 404 });
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.pathname.includes(PREVIEW_PREFIX)) {
    event.respondWith(handlePreviewRequest(url));
  }
});
