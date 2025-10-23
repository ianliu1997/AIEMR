#!/usr/bin/env node
/**
 * Thin helper that reminds developers to enable MSW in the browser console.
 * Next.js recommends starting the worker inside the app entrypoint instead.
 */
console.info("To enable MSW in the browser, import `worker.start()` inside a client component or _app.tsx.");
