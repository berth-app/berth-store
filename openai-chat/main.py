"""OpenAI Chat Wrapper — HTTP API for chat completions

Exposes a simple POST /chat endpoint that wraps OpenAI's chat API.
Supports streaming, system prompts, and conversation history.

Set OPENAI_API_KEY env var. Optionally set MODEL and PORT.
"""

import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from openai import OpenAI

API_KEY = os.environ.get("OPENAI_API_KEY")
if not API_KEY:
    print("Error: OPENAI_API_KEY environment variable not set")
    exit(1)

MODEL = os.environ.get("MODEL", "gpt-4o-mini")
PORT = int(os.environ.get("PORT", "8080"))
SYSTEM_PROMPT = os.environ.get("SYSTEM_PROMPT", "You are a helpful assistant.")

client = OpenAI(api_key=API_KEY)


class ChatHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._json_response({"status": "ok", "model": MODEL})
        else:
            self._json_response(
                {"endpoints": {"POST /chat": "Send a chat message", "GET /health": "Health check"}}
            )

    def do_POST(self):
        if self.path != "/chat":
            self._json_response({"error": "Not found"}, 404)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        message = body.get("message", "")
        history = body.get("history", [])
        system = body.get("system_prompt", SYSTEM_PROMPT)

        if not message:
            self._json_response({"error": "message field is required"}, 400)
            return

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": message})

        try:
            response = client.chat.completions.create(model=MODEL, messages=messages)
            reply = response.choices[0].message.content
            self._json_response({
                "reply": reply,
                "model": MODEL,
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                },
            })
        except Exception as e:
            self._json_response({"error": str(e)}, 500)

    def _json_response(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ChatHandler)
    print(f"OpenAI Chat Wrapper running on port {PORT} (model: {MODEL})")
    server.serve_forever()
