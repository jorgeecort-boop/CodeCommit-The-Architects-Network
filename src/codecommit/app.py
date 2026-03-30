import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import DB_PATH, HOST, PORT
from .db import Database
from .service import CodeCommitService, DomainError


DB = Database(DB_PATH)
SERVICE = CodeCommitService(DB)
WEB_DIR = Path(__file__).resolve().parent / "web"


class ApiHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, payload: str, status=HTTPStatus.OK, content_type="text/html; charset=utf-8"):
        body = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            html_path = WEB_DIR / "index.html"
            return self._send_text(html_path.read_text(encoding="utf-8"))

        if path == "/api/health":
            return self._send_json({"ok": True, "service": "codecommit"})

        if path.startswith("/api/users/"):
            user_id = int(path.split("/")[-1])
            user = SERVICE.get_user(user_id)
            return self._send_json(user)

        if path == "/api/match":
            qs = parse_qs(parsed.query)
            user_id = int(qs["user_id"][0])
            target_id = int(qs["target_id"][0])
            result = SERVICE.compatibility(user_id, target_id)
            return self._send_json(result)

        if path == "/api/chat/messages":
            qs = parse_qs(parsed.query)
            chat_id = int(qs["chat_id"][0])
            result = SERVICE.list_messages(chat_id)
            return self._send_json({"messages": result})

        return self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            if parsed.path == "/api/register":
                user = SERVICE.register_user(payload)
                return self._send_json(user, status=HTTPStatus.CREATED)

            if parsed.path == "/api/pull-requests":
                result = SERVICE.send_pull_request(
                    from_user_id=int(payload["from_user_id"]),
                    to_user_id=int(payload["to_user_id"]),
                )
                return self._send_json(result, status=HTTPStatus.CREATED)

            if parsed.path == "/api/pull-requests/merge":
                result = SERVICE.merge_pull_request(int(payload["pull_request_id"]))
                return self._send_json(result)

            if parsed.path == "/api/chat/message":
                result = SERVICE.send_message(
                    chat_id=int(payload["chat_id"]),
                    sender_id=int(payload["sender_id"]),
                    body=str(payload["body"]),
                )
                return self._send_json(result, status=HTTPStatus.CREATED)

            if parsed.path == "/api/github/import":
                result = SERVICE.import_github_languages(
                    user_id=int(payload["user_id"]),
                    github_username=str(payload["github_username"]),
                    github_token=payload.get("github_token"),
                )
                return self._send_json(result)
        except DomainError as err:
            return self._send_json({"error": str(err)}, status=HTTPStatus.BAD_REQUEST)
        except KeyError as err:
            return self._send_json(
                {"error": f"Falta campo requerido: {err}"},
                status=HTTPStatus.BAD_REQUEST,
            )
        except Exception as err:  # pragma: no cover
            return self._send_json(
                {"error": f"Internal error: {err}"},
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
            )

        return self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def run():
    server = ThreadingHTTPServer((HOST, PORT), ApiHandler)
    print(f"CodeCommit API running on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()

