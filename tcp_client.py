import socket

# Define server address and port
SERVER_HOST = '127.0.0.1'   # localhost
SERVER_PORT = 12345         # same port as your server

# Create a TCP socket
client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# Connect to the server
client_socket.connect((SERVER_HOST, SERVER_PORT))
print(f"Connected to server {SERVER_HOST}:{SERVER_PORT}")

# Send a message
message = "Hello Server!"
client_socket.send(message.encode())

# Receive response from server
response = client_socket.recv(1024).decode()
print(f"Server replied: {response}")

# Close the connection
client_socket.close()
