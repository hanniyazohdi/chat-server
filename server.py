import socket
import os
import signal
import sys
import selectors
import json

# Selector for helping us select incoming data and connections from multiple sources.

sel = selectors.DefaultSelector()

# Client list for mapping connected clients to their connections.
# follow list dictionary for collecting followed terms and users

client_list = []
follow_list = {}

# Signal handler for graceful exiting.  We let clients know in the process so they can disconnect too.

def signal_handler(sig, frame):
    print('Interrupt received, shutting down ...')
    message='DISCONNECT CHAT/1.0\n'
    for reg in client_list:
        reg[1].send(message.encode())
    sys.exit(0)

# Read a single line (ending with \n) from a socket and return it.
# We will strip out the \r and the \n in the process.

def get_line_from_socket(sock):

    done = False
    line = ''
    while (not done):
        char = sock.recv(1).decode()
        if (char == '\r'):
            pass
        elif (char == '\n'):
            done = True
        else:
            line = line + char
    return line

# Search the client list for a particular user.

def client_search(user):
    for reg in client_list:
        if reg[0] == user:
            return reg[1]
    return None

# Search the client list for a particular user by their socket.

def client_search_by_socket(sock):
    for reg in client_list:
        if reg[1] == sock:
            return reg[0]
    return None

# Add a user to the client list.

def client_add(user, conn):
    if user == "all":
        response='Cannot register as @all'
        conn.send(response.encode())
        conn.close()
    registration = (user, conn)
    client_list.append(registration)
    follow_list[user] = ['@'+user, '@all']

# Remove a client when disconnected.

def client_remove(user):
    for reg in client_list:
        if reg[0] == user:
            client_list.remove(reg)
            break

# Function to read messages from clients.

def read_message(sock, mask):
    message = get_line_from_socket(sock)
    # Does this indicate a closed connection?

    if message == '':
        print('Closing connection')
        sel.unregister(sock)
        sock.close()

    # Receive the message.  

    else:
        user = client_search_by_socket(sock)
        words = message.split(' ')
        print(f'Received message from user {user}:  ' + message)
        
        # Check for client disconnections.  
 
        if words[1] == 'DISCONNECT' or words[1] == '!exit':
            
            print('Disconnecting user ' + user)
            for reg in client_list:
                if reg[0] == user:
                    client_sock = reg[1]
                    forwarded_message = f'Disconnected from server ... exiting!\n'
                    client_sock.send(forwarded_message.encode())
            client_remove(user)
            sel.unregister(sock)
            sock.close()
        # send client list to sender (client_list)
        elif words[1] == '!list':

            for reg in client_list:
                if reg[0] == user:
                    client_sock = reg[1]
                    names = f'Active users: {list(i[0] for i in client_list)} \n'
                    client_sock.send(names.encode())
            
        elif words[1] == '!follow':
            for reg in client_list:
                if reg[0] == user and words[2] not in follow_list[user]:
                    follow_list[user].append(words[2])
                    client_sock = reg[1]
                    notice = f'You are now following {words[2]} \n'
                    client_sock.send(notice.encode())

        elif words[1] == '!unfollow':
            for reg in client_list:
                if reg[0] == user:
                    if words[2] not in follow_list[user] or words[2] == "@all" or words[2] == user:
                        client_sock = reg[1]
                        error = f'Error! Unable to unfollow {words[2]}\n'
                        client_sock.send(error.encode())
                    else:
                        follow_list[user].remove(words[2])
                        client_sock = reg[1]
                        notice = f'Unfollowed {words[2]} \n'
                        client_sock.send(notice.encode())
                    
        elif words[1] == '!follow?':
            for reg in client_list:
                if reg[0] == user:
                    client_sock = reg[1]
                    following = f"Following: {json.dumps(follow_list[user]).strip('[]')} \n"
                    client_sock.send(following.encode())

        else:
            for reg in send_message_to(follow_list, message):
                client_sock = client_search(reg)
                forwarded_message = f'{message}\n'
                client_sock.send(forwarded_message.encode())


def users_who_follow_this_term(term):
    result = []
    for user in follow_list.keys():
        if term in follow_list[user]:
            result.append(user)
    return result
  
def send_message_to(follow_list, message):
    message_splitted = message.split()
    followers = []
    for word in message_splitted:
        for user in follow_list.keys():
            if word in follow_list[user]:
                followers.append(user)
    return set(followers)


# Function to accept and set up clients.

def accept_client(sock, mask):
    conn, addr = sock.accept()
    print('Accepted connection from client address:', addr)
    message = get_line_from_socket(conn)
    message_parts = message.split()

    # Check format of request.

    if ((len(message_parts) != 3) or (message_parts[0] != 'REGISTER') or (message_parts[2] != 'CHAT/1.0')):
        print('Error:  Invalid registration message.')
        print('Received: ' + message)
        print('Connection closing ...')
        response='400 Invalid registration\n'
        conn.send(response.encode())
        conn.close()

    # If request is properly formatted and user not already listed, go ahead with registration.

    else:
        user = message_parts[1]

        if (client_search(user) == None):
            client_add(user,conn)
            print(f'Connection to client established, waiting to receive messages from user \'{user}\'...')
            response='200 Registration succesful\n'
            conn.send(response.encode())
            conn.setblocking(False)
            sel.register(conn, selectors.EVENT_READ, read_message)

        # If user already in list, return a registration error.

        else:
            print('Error:  Client already registered.')
            print('Connection closing ...')
            response='401 Client already registered\n'
            conn.send(response.encode())
            conn.close()


# Our main function.

def main():

    # Register our signal handler for shutting down.

    signal.signal(signal.SIGINT, signal_handler)

    # Create the socket.  We will ask this to work on any interface and to pick
    # a free port at random.  We'll print this out for clients to use.

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('', 0))
    print('Will wait for client connections at port ' + str(server_socket.getsockname()[1]))
    server_socket.listen(100)
    server_socket.setblocking(False)
    sel.register(server_socket, selectors.EVENT_READ, accept_client)
    print('Waiting for incoming client connections ...')
     
    # Keep the server running forever, waiting for connections or messages.
    
    while(True):
        events = sel.select()
        for key, mask in events:
            callback = key.data
            callback(key.fileobj, mask)    

if __name__ == '__main__':
    main()

