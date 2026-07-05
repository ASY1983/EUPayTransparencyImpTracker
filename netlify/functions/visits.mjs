// Visit counter for the EU Pay Transparency Directive Tracker.
// Storage: Netlify Blobs (no external database, no account beyond Netlify).
// POST = count a new visit and return the total (one per browser session,
//        deduplicated client-side via sessionStorage).
// GET  = return the current total without incrementing.
import { getStore } from "@netlify/blobs";

export default async (req) => {
  const store = getStore("visits");
  let count = Number(await store.get("total")) || 0;

  if (req.method === "POST") {
    count += 1;
    await store.set("total", String(count));
  }

  return new Response(JSON.stringify({ count }), {
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
};

export const config = { path: "/.netlify/functions/visits" };
