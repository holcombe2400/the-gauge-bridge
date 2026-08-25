#!/usr/bin/env python3
"""The Gauge Relay: local WU-protocol endpoint for Vevor YT60234 consoles."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import hashlib
import hmac
import json
import logging
import socket
import threading
import time

OPTIONS_PATH = Path("/data/options.json")
QUEUE_PATH = Path("/data/pending-packet.json")
STATUS_PATH = Path("/data/relay-status.json")
last_forward_at = 0.0
pending_packet = None
UPLOAD_HOST = "rtupdate.wunderground.com"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def options():
    if not OPTIONS_PATH.exists():
        raise RuntimeError("Home Assistant has not supplied relay options yet.")
    return json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))

def save_pending(packet):
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(packet, separators=(",", ":")), encoding="utf-8")

def utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def status():
    if not STATUS_PATH.exists():
        return {"lastStationPacketAt": None, "lastDeliveredAt": None, "lastError": None}
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"lastStationPacketAt": None, "lastDeliveredAt": None, "lastError": "Relay status could not be read"}

def save_status(**changes):
    current = status()
    current.update(changes)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(current, separators=(",", ":")), encoding="utf-8")

def local_ip():
    """Return the LAN address other devices should use to reach this host."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("1.1.1.1", 53))
        return probe.getsockname()[0]
    finally:
        probe.close()

def dns_question(packet):
    if len(packet) < 17:
        raise ValueError("DNS request is too short")
    labels, position = [], 12
    while True:
        length = packet[position]
        position += 1
        if length == 0:
            break
        if length > 63 or position + length > len(packet):
            raise ValueError("DNS question is malformed")
        labels.append(packet[position:position + length].decode("ascii"))
        position += length
    if position + 4 > len(packet):
        raise ValueError("DNS question is incomplete")
    question_end = position + 4
    query_type = int.from_bytes(packet[position:position + 2], "big")
    return ".".join(labels).lower(), query_type, question_end

def local_dns_answer(packet, question_end):
    header = packet[:2] + b"\x81\x80" + b"\x00\x01\x00\x01\x00\x00\x00\x00"
    answer = b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04" + socket.inet_aton(local_ip())
    return header + packet[12:question_end] + answer

def forward_dns(packet, upstream):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(3)
        client.sendto(packet, (upstream, 53))
        return client.recv(4096)

def serve_dns():
    config = options()
    upstream = config.get("upstream_dns", "1.1.1.1")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", 53))
        logging.info("Local DNS listening on port 53; redirecting %s to %s", UPLOAD_HOST, local_ip())
        while True:
            packet, address = server.recvfrom(4096)
            try:
                hostname, query_type, question_end = dns_question(packet)
                if hostname == UPLOAD_HOST and query_type in (1, 255):
                    response = local_dns_answer(packet, question_end)
                    save_status(lastDnsRedirectAt=utc_now(), lastError=None)
                else:
                    response = forward_dns(packet, upstream)
                server.sendto(response, address)
            except Exception as error:
                save_status(lastError=f"DNS: {error}")
                logging.warning("DNS request failed: %s", error)

def forward(packet):
    config = options()
    body = json.dumps({"packet": packet}, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(config["relay_secret"].encode("utf-8"), body, hashlib.sha256).hexdigest()
    request = Request(config["gauge_url"], data=body, method="POST", headers={
        "content-type": "application/json",
        "x-gauge-station": config["station_code"],
        "x-gauge-secret": config["relay_secret"],
        "x-gauge-signature": signature,
    })
    with urlopen(request, timeout=12) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"The Gauge returned HTTP {response.status}")

def receive(packet):
    global last_forward_at, pending_packet
    pending_packet = packet
    config = options()
    interval = int(config.get("upload_interval_seconds", 60))
    if time.monotonic() - last_forward_at < interval:
        return
    try:
        # Prefer the newest packet received while a prior delivery was waiting.
        if QUEUE_PATH.exists():
            pending_packet = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        forward(pending_packet)
        QUEUE_PATH.unlink(missing_ok=True)
        pending_packet = None
        last_forward_at = time.monotonic()
        save_status(lastDeliveredAt=utc_now(), lastError=None)
        logging.info("Delivered station reading to The Gauge")
    except Exception as error:
        save_pending(pending_packet)
        save_status(lastError=str(error))
        logging.warning("Gauge delivery deferred: %s", error)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logging.info("%s - %s", self.address_string(), format % args)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            relay_status = status()
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "queued": QUEUE_PATH.exists(), **relay_status}).encode("utf-8"))
            return
        if parsed.path != "/weatherstation/updateweatherstation.php":
            self.send_error(404)
            return
        values = {key: value[-1] for key, value in parse_qs(parsed.query, keep_blank_values=True).items()}
        try:
            config = options()
            if values.get("ID") != config["station_code"] or values.get("PASSWORD") != config["relay_secret"]:
                raise PermissionError("Station ID or key did not match this relay")
            save_status(lastStationPacketAt=utc_now(), lastError=None)
            receive(values)
            self.send_response(200)
            self.send_header("content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"success")
        except PermissionError as error:
            logging.warning("Rejected station packet: %s", error)
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"invalid station credentials")
        except Exception as error:
            logging.exception("Relay request failed")
            self.send_response(503)
            self.end_headers()
            self.wfile.write(f"relay unavailable: {error}".encode("utf-8"))

if __name__ == "__main__":
    threading.Thread(target=serve_dns, daemon=True).start()
    logging.info("The Gauge Bridge listening on ports 53 and 80")
    ThreadingHTTPServer(("0.0.0.0", 80), Handler).serve_forever()
