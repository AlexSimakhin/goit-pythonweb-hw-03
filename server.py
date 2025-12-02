import asyncio
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from multiprocessing import Process
import os
import json
from datetime import datetime
import websockets
from jinja2 import Environment, FileSystemLoader

logging.basicConfig(level=logging.INFO)

DATA_FILE = "storage/data.json"

if not os.path.exists("storage"):
    os.makedirs("storage")


class HttpHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path == "/":
            self.send_html_file("pages/index.html")
        elif parsed_url.path == "/message.html":
            self.send_html_file("pages/message.html")
        elif parsed_url.path == "/read":
            self.show_messages()
        elif parsed_url.path.startswith("/static/"):
            self.send_static_file(parsed_url.path[1:])
        else:
            self.send_html_file("pages/error.html", 404)

    def do_POST(self):
        content_length = int(self.headers["Content-Length"])
        post_data = self.rfile.read(content_length)
        parsed_data = parse_qs(post_data.decode("utf-8"))
        username = parsed_data.get("username")[0]
        message = parsed_data.get("message")[0]

        message_data = {
            "username": username,
            "message": message,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        self.save_message_to_json(message_data)

        async def send_message():
            uri = "ws://localhost:6000"
            async with websockets.connect(uri) as websocket:
                await websocket.send(json.dumps(message_data))

        asyncio.run(send_message())

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        with open("pages/message_sent.html", "rb") as file:
            self.wfile.write(file.read())

    def send_html_file(self, filename, status=200):
        self.send_response(status)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        with open(filename, "rb") as file:
            self.wfile.write(file.read())

    def send_static_file(self, filename, status=200):
        try:
            if not filename.startswith("static/"):
                filepath = f"static/{filename}"
            else:
                filepath = filename
            with open(filepath, "rb") as file:
                self.send_response(status)
                if filepath.endswith(".css"):
                    self.send_header("Content-type", "text/css")
                elif filepath.endswith(".png"):
                    self.send_header("Content-type", "image/png")

                self.end_headers()
                self.wfile.write(file.read())
        except FileNotFoundError:
            self.send_html_file("pages/error.html", 404)

    def save_message_to_json(self, message_data):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            data = {}

        new_data = {message_data["timestamp"]: {
            "username": message_data["username"],
            "message": message_data["message"],
        }}
        new_data.update(data)

        with open(DATA_FILE, "w", encoding="utf-8") as file:
            json.dump(new_data, file, indent=4, ensure_ascii=False)

    def show_messages(self):
        env = Environment(loader=FileSystemLoader("templates"))
        template = env.get_template("read.html")

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as file:
                messages = json.load(file)
        except (FileNotFoundError, json.JSONDecodeError):
            messages = {}

        logging.info("Loaded %d messages from %s", len(messages), DATA_FILE)

        html_content = template.render(messages=messages)

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))


class WebSocketServer:
    async def ws_handler(self, websocket):
        async for message in websocket:
            data = json.loads(message)
            logging.info("Received message: %s", data)


async def run_websocket_server():
    server = WebSocketServer()
    async with websockets.serve(server.ws_handler, "0.0.0.0", 6000):
        logging.info("WebSocket server started on port 6000")
        await asyncio.Future()


def start_websocket_server():
    asyncio.run(run_websocket_server())


def run_http_server():
    server_address = ("", 3000)
    httpd = HTTPServer(server_address, HttpHandler)
    logging.info("HTTP server started on port 3000")
    httpd.serve_forever()


if __name__ == "__main__":
    http_process = Process(target=run_http_server)
    ws_process = Process(target=start_websocket_server)

    http_process.start()
    ws_process.start()

    http_process.join()
    ws_process.join()
