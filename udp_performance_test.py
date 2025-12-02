
import socket
import sys
import time
from statistics import mean

from common import pack_message, unpack_message

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 6000

def run_perf_test(
    username: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    num_messages: int = 100,
    payload_size: int = 32,
    timeout: float = 0.5,
):
    """
    Simple sequential latency/loss test.
    Sends num_messages chat packets and waits for ACKs.
    Measures RTT and loss rate.
    """
    server_addr = (host, port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)

    # 1) Join first so the server knows this user
    join_raw = pack_message("join", username, text="perf test join", seq=0)
    sock.sendto(join_raw, server_addr)

    print(
        f"[perf] Running UDP performance test against {host}:{port} "
        f"(messages={num_messages}, payload={payload_size} bytes, timeout={timeout}s)"
    )

    rtts = []          # list of round-trip times in ms
    sent = 0
    received = 0

    for i in range(1, num_messages + 1):
        text = f"ping-{i}-".ljust(payload_size, "x")
        seq = i  # use i as sequence number for simplicity

        raw = pack_message("chat", username, text=text, seq=seq)
        start = time.perf_counter()
        sock.sendto(raw, server_addr)
        sent += 1

        try:
            while True:
                data, addr = sock.recvfrom(65535)
                ok, obj, err = unpack_message(data)
                if not ok or obj is None:
                    # bad checksum, ignore this packet and continue waiting
                    print(f"[perf] Ignoring corrupt packet: {err}")
                    continue

                msg = obj["msg"]
                kind = msg.get("kind")
                ack_seq = msg.get("seq")

                # We only care about ACKs for this specific seq
                if kind == "ack" and ack_seq == seq:
                    rtt_ms = (time.perf_counter() - start) * 1000.0
                    rtts.append(rtt_ms)
                    received += 1
                    break
                else:
                    # Some other packet; ignore for this test
                    continue

        except socket.timeout:
            # No ACK received within timeout
            print(f"[perf] WARNING: no ACK for seq={seq} within {timeout}s (possible loss)")
            continue

    sock.close()

    # ----- Report results -----
    lost = sent - received
    loss_rate = (lost / sent) * 100.0 if sent > 0 else 0.0

    print("\n[perf] === UDP Performance Results ===")
    print(f"  Total sent:         {sent}")
    print(f"  Total acks recv:    {received}")
    print(f"  Lost (no ack):      {lost}")
    print(f"  Loss rate:          {loss_rate:.2f}%")

    if rtts:
        print(f"  Min RTT:            {min(rtts):.2f} ms")
        print(f"  Max RTT:            {max(rtts):.2f} ms")
        print(f"  Avg RTT:            {mean(rtts):.2f} ms")
    else:
        print("  No RTT samples (all messages lost or timed out).")

    print("[perf] =================================\n")


def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <username> [host] [port] [num_messages]")
        print(f"Defaults: host={DEFAULT_HOST}, port={DEFAULT_PORT}, num_messages=100")
        sys.exit(1)

    username = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HOST
    port = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PORT
    num_messages = int(sys.argv[4]) if len(sys.argv) > 4 else 100

    # You can tweak these defaults if needed
    payload_size = 32
    timeout = 0.5

    run_perf_test(
        username=username,
        host=host,
        port=port,
        num_messages=num_messages,
        payload_size=payload_size,
        timeout=timeout,
    )


if __name__ == "__main__":
    main()
