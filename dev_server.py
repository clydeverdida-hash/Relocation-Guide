"""
Local preview: serves /public and routes POST /api/lead to api/lead.py.

    python dev_server.py            # DRY_RUN on: no Lofty/email calls, submissions printed to the console
    python dev_server.py --live     # uses real keys from your environment (LOFTY_API_KEY, RESEND_API_KEY, ...)

Then open http://localhost:8080
"""
import functools
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "api"))
if "--live" not in sys.argv:
    os.environ["DRY_RUN"] = "true"

import lead  # noqa: E402


class DevHandler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path.split("?")[0] == "/api/lead":
            lead.handler.do_POST(self)
        else:
            self.send_error(404)

    _send = lead.handler._send


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    Handler = functools.partial(DevHandler, directory=os.path.join(ROOT, "public"))
    mode = "LIVE" if "--live" in sys.argv else "DRY_RUN"
    print(f"Serving on http://localhost:{port}  ({mode})")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
