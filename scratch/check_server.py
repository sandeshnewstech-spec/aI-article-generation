import socket
import sys

def check_port(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        try:
            s.connect((host, port))
            print(f"Port {port} on {host} is OPEN")
            s.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
            data = s.recv(1024)
            print(f"Received data: {data[:100]}...")
        except Exception as e:
            print(f"FAILED to connect to {host}:{port}: {e}")

if __name__ == "__main__":
    check_port("127.0.0.1", 8000)
