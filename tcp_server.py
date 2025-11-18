# tcp_server.py
import socket
import threading
import json
import hashlib
from datetime import datetime

HOST = "127.0.0.1"
PORT = 8888

clients_lock = threading.Lock()
# conn -> {"user": str, "addr": (ip, port)}
clients = {}

def ts_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def line_send(conn, obj: dict):
    try:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        conn.sendall(data)
    except Exception:
        pass

def make_hash(user: str, ts: str, text: str) -> str:
    # Simple integrity check (checksum/hash)
    return hashlib.sha256(f"{user}|{ts}|{text}".encode("utf-8")).hexdigest()

def broadcast(obj: dict, exclude=None):
    with clients_lock:
        dead = []
        for c in list(clients.keys()):
            if c is exclude:
                continue
            try:
                line_send(c, obj)
            except Exception:
                dead.append(c)
        for d in dead:
            try:
                d.close()
            except:
                pass
            clients.pop(d, None)

def list_users():
    with clients_lock:
        return sorted(info["user"] for info in clients.values())

def get_conn_by_name(name: str):
    with clients_lock:
        for c, info in clients.items():
            if info["user"].lower() == name.lower():
                return c
    return None

def handle_command(conn, user, text):
    parts = text.strip().split(" ", 2)
    cmd = parts[0].lower()

    if cmd == "/quit":
        line_send(conn, {"type": "server", "text": "Goodbye!"})
        return "quit"

    if cmd == "/list":
        users = ", ".join(list_users()) or "(no users)"
        line_send(conn, {"type": "server", "text": f"Online: {users}"})
        return "ok"

    if cmd == "/whisper" and len(parts) >= 3:
        target = parts[1]
        msg = parts[2]
        target_conn = get_conn_by_name(target)
        if target_conn is None:
            line_send(conn, {"type": "server", "text": f"User '{target}' not found."})
        else:
            ts = ts_now()
            h = make_hash(user, ts, msg)
            # to target
            line_send(target_conn, {"type": "whisper", "user": user, "ts": ts, "text": msg, "hash": h})
            # confirm to sender
            line_send(conn, {"type": "server", "text": f"(whisper to {target}) {msg}"})
        return "ok"

    line_send(conn, {"type": "server", "text": "Unknown command. Try /list, /whisper <user> <msg>, /quit"})
    return "ok"

def handle_client(conn, addr):
    left_announced = False
    try:
        f = conn.makefile("rb")
        # Expect hello with username
        hello_line = f.readline()
        if not hello_line:
            conn.close()
            return
        hello = json.loads(hello_line.decode(errors="ignore"))
        username = (hello.get("user") or f"Guest{addr[1]}").strip()

        # Ensure unique username
        with clients_lock:
            base = username
            i = 1
            while any(info["user"].lower() == username.lower() for info in clients.values()):
                username = f"{base}{i}"
                i += 1
            clients[conn] = {"user": username, "addr": addr}

        # Welcome + joined broadcast
        line_send(conn, {"type": "server", "text": f"Welcome, {username}! Commands: /list, /whisper <user> <msg>, /quit"})
        broadcast({"type": "info", "text": f"* {username} joined *", "ts": ts_now()}, exclude=None)
        print(f"[+] {addr} -> {username} connected")

        # Message loop
        for raw in f:
            try:
                msg = json.loads(raw.decode(errors="ignore"))
            except Exception:
                line_send(conn, {"type": "error", "text": "Invalid JSON message."})
                continue

            mtype = msg.get("type")
            if mtype == "chat":
                text = str(msg.get("text", ""))
                ts = str(msg.get("ts", ""))
                user_from = clients.get(conn, {}).get("user", "?")
                rx_hash = str(msg.get("hash", ""))
                calc_hash = make_hash(user_from, ts, text)
                if rx_hash != calc_hash:
                    line_send(conn, {"type": "error", "text": "Integrity check failed. Message dropped."})
                    continue
                broadcast({"type": "chat", "user": user_from, "ts": ts, "text": text, "hash": calc_hash}, exclude=None)

            elif mtype == "cmd":
                text = str(msg.get("text", ""))
                status = handle_command(conn, clients[conn]["user"], text)
                if status == "quit":
                    # Announce before closing, and to everyone except the quitter
                    user = clients.get(conn, {}).get("user", "Unknown")
                    broadcast({"type": "info", "text": f"* {user} left *", "ts": ts_now()}, exclude=conn)
                    left_announced = True
                    # Goodbye already sent in handle_command
                    raise ConnectionAbortedError("user quit")

            else:
                line_send(conn, {"type": "error", "text": "Unknown message type."})

    except Exception:
        pass
    finally:
        user = None
        with clients_lock:
            info = clients.pop(conn, None)
            if info:
                user = info["user"]
        try:
            conn.close()
        except:
            pass
        if user:
            if not left_announced:
                broadcast({"type": "info", "text": f"* {user} left *", "ts": ts_now()}, exclude=None)
            print(f"[-] {addr} -> {user} disconnected")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # If Windows complains, comment the next line
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen(50)
        print(f"Listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
