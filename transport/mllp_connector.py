from __future__ import annotations

import logging
import queue
import socket
import threading
import uuid
from typing import Optional

from healthcare_sdk import Adapter, RawMessage

MLLP_START = b"\x0b"
MLLP_END = b"\x1c\x0d"

logger = logging.getLogger(__name__)


class MllpConnector(Adapter):
    """TCP socket server that speaks MLLP (Minimal Lower Layer Protocol) for HL7v2 messages."""

    def __init__(self, host: str = "0.0.0.0", port: int = 2575) -> None:
        self._host = host
        self._port = port
        self._message_queue: queue.Queue[RawMessage] = queue.Queue()
        self._server_thread: Optional[threading.Thread] = None
        self._running = False

    def executeServer(self, port: Optional[int] = None) -> None:
        """Start the MLLP TCP server (blocking until stopped)."""
        if port is not None:
            self._port = port

        self._running = True
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_sock:
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind((self._host, self._port))
            server_sock.listen(5)
            logger.info("MLLP server listening on %s:%d", self._host, self._port)

            while self._running:
                try:
                    server_sock.settimeout(1.0)
                    conn, addr = server_sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True,
                )
                client_thread.start()

    def _handle_client(self, conn: socket.socket, addr: tuple) -> None:
        logger.debug("MLLP connection from %s", addr)
        with conn:
            buffer = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                except OSError:
                    break
                if not chunk:
                    break

                buffer += chunk

                while True:
                    start = buffer.find(MLLP_START)
                    if start == -1:
                        buffer = b""
                        break

                    end = buffer.find(MLLP_END, start + 1)
                    if end == -1:
                        buffer = buffer[start:]
                        break

                    raw_hl7 = buffer[start + 1 : end]
                    buffer = buffer[end + len(MLLP_END) :]

                    raw_msg = self._parse_hl7(raw_hl7)
                    self._message_queue.put(raw_msg)

                    ack = self._build_ack(raw_hl7, raw_msg.id)
                    conn.sendall(MLLP_START + ack + MLLP_END)

    def _parse_hl7(self, raw_hl7: bytes) -> RawMessage:
        msg_id = str(uuid.uuid4())
        text = raw_hl7.decode("latin-1", errors="replace")
        message_type: Optional[str] = None

        try:
            lines = text.replace("\r", "\n").strip().splitlines()
            for line in lines:
                if line.startswith("MSH"):
                    fields = line.split("|")
                    if len(fields) > 8:
                        message_type = fields[8].split("^")[0] if fields[8] else None
                    break
        except Exception:
            pass

        return RawMessage(
            id=msg_id,
            protocol="HL7v2",
            raw_payload=text,
            message_type=message_type,
            metadata={"source": "mllp"},
        )

    def _build_ack(self, raw_hl7: bytes, msg_id: str) -> bytes:
        """Build a minimal HL7v2 ACK message."""
        try:
            text = raw_hl7.decode("latin-1", errors="replace")
            lines = text.replace("\r", "\n").strip().splitlines()
            msh_fields = []
            for line in lines:
                if line.startswith("MSH"):
                    msh_fields = line.split("|")
                    break

            sending_app = msh_fields[2] if len(msh_fields) > 2 else ""
            sending_facility = msh_fields[3] if len(msh_fields) > 3 else ""
            receiving_app = msh_fields[4] if len(msh_fields) > 4 else ""
            receiving_facility = msh_fields[5] if len(msh_fields) > 5 else ""
            orig_msg_id = msh_fields[9] if len(msh_fields) > 9 else msg_id
            version = msh_fields[11] if len(msh_fields) > 11 else "2.5"
        except Exception:
            sending_app = sending_facility = receiving_app = receiving_facility = ""
            orig_msg_id = msg_id
            version = "2.5"

        import datetime
        now = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

        ack_text = (
            f"MSH|^~\\&|{receiving_app}|{receiving_facility}|{sending_app}|{sending_facility}"
            f"|{now}||ACK|{msg_id}|P|{version}\r"
            f"MSA|AA|{orig_msg_id}\r"
        )
        return ack_text.encode("latin-1")

    def receive(self) -> RawMessage:
        """Block until an MLLP message arrives and return it."""
        return self._message_queue.get()

    def start_in_background(self) -> None:
        """Start the MLLP server in a daemon thread (non-blocking)."""
        self._server_thread = threading.Thread(
            target=self.executeServer,
            daemon=True,
        )
        self._server_thread.start()

    def stop(self) -> None:
        self._running = False
