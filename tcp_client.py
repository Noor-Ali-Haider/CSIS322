# tcp_client.py
import socket
import threading
import json
import hashlib
import sys
from datetime import datetime

HOST = "127.0.0.1"
PORT = 8888

def ts_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def make_hash(user: str, ts: str, text: str) -> str:
    return hashlib.sha256(f"{user}|{ts}|{text}".encode("utf-8")).hexdigest()

def recv_loop(sock):
    try:
        f = sock.makefile("rb")
        for raw in f:
            try:
                msg = json.loads(raw.decode(errors="ignore"))
            except Exception:
                print("[client] Received invalid JSON.")
                continue

            t = msg.get("type")
            if t == "server":
                print(msg.get("text", ""))
            elif t == "info":
                print(f"[{msg.get('ts','')}] {msg.get('text','')}")
            elif t == "chat":
                user = msg.get("user", "?")
                ts = msg.get("ts", "")
                text = msg.get("text", "")
                rx_hash = msg.get("hash", "")
                calc = make_hash(user, ts, text)
                if rx_hash != calc:
                    print(f"[WARN] Integrity check failed for message from {user}.")
                print(f"[{ts}] {user}: {text}")
            elif t == "whisper":
                user = msg.get("user", "?")
                ts = msg.get("ts", "")
                text = msg.get("text", "")
                rx_hash = msg.get("hash", "")
                calc = make_hash(user, ts, text)
                if rx_hash != calc:
                    print(f"[WARN] Integrity check failed for whisper from {user}.")
                print(f"[{ts}] (whisper) {user}: {text}")
            elif t == "error":
                print(f"[error] {msg.get('text','')}")
            else:
                print(f"[client] Unknown type: {t}")
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except:
            pass
        print("[client] Connection closed.")

def main():
    name = input("Enter your name: ").strip() or "Client"
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect((HOST, PORT))
        # Send hello (username)
        hello = {"type": "hello", "user": name}
        s.sendall((json.dumps(hello) + "\n").encode())

        # Start receiver
        threading.Thread(target=recv_loop, args=(s,), daemon=True).start()

        print("Type your messages. Commands: /list, /whisper <user> <msg>, /quit")
        while True:
            try:
                line = input("> ")
            except EOFError:
                line = "/quit"

            if not line:
                continue

            if line.startswith("/"):
                cmd = {"type": "cmd", "text": line}
                s.sendall((json.dumps(cmd) + "\n").encode())
                if line.strip().lower() == "/quit":
                    print("You left the chat.")
                    break
                continue

            ts = ts_now()
            h = make_hash(name, ts, line)
            payload = {"type": "chat", "user": name, "ts": ts, "text": line, "hash": h}
            s.sendall((json.dumps(payload) + "\n").encode())

if __name__ == "__main__":
    main()
