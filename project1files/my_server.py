# CITS3002 2021 Assignment
#
# This file implements a basic server that allows a single client to play a
# single game with no other participants, and very little error checking.
#
# Any other clients that connect during this time will need to wait for the
# first client's game to complete.
#
# Your task will be to write a new server that adds all connected clients into
# a pool of players. When enough players are available (two or more), the server
# will create a game with a random sample of those players (no more than
# tiles.PLAYER_LIMIT players will be in any one game). Players will take turns
# in an order determined by the server, continuing until the game is finished
# (there are less than two players remaining). When the game is finished, if
# there are enough players available the server will start a new game with a
# new selection of clients.

# CITS3002 Server Project - Sockets.
# Jakub Wysocki (22716248)
# Some code adapted from RealPython: https://realpython.com/python-sockets/#handling-multiple-connections

import socket
import sys
import tiles
import selectors
import types
import random
import time

MAX_PLAYERS = 3
WON_DELAY_S = 4

# connections
sel = selectors.DefaultSelector()
live_idnums = []
client_connections = []
# flags/parameters which outline the current game state
board = tiles.Board()
currentTurn = 0
started_idnums = []
first_start = True
joined_msgs = []
eliminated_clients = []
disconnected_clients = []

""" HANDLES CLIENT CONNECTIONS """
def client_handler(key, mask):

  # - SET UP DATA -
  data = key.data
  host, port = data.addr
  name = '{}:{}'.format(host, port)
  idnum = data.idnum
  


  # - GLOBALS -
  global currentTurn
  global first_start
  global joined_msgs
  global started_idnums
  global eliminated_clients

  # if a player leaves before every active player makes a turn, the client crashes...
  msg = receive_msg_client(key, mask, idnum)

  # --  NEW PLAYER JOINS --
  if idnum not in live_idnums:
    new_player_joined(name, idnum)

  # -- START FIRST GAME --
  if len(live_idnums) >= MAX_PLAYERS:
    if first_start:
      first_start = False
      start_new_game()
  else:
    # - CANNOT CONTINUE UNLESS SUFFICIENT PLAYERS CONNECTED -
    return
  
  # -- SKIP DISCONNECTED PLAYERS --
  if started_idnums[currentTurn] in disconnected_clients:
    currentTurn += 1
    if currentTurn > MAX_PLAYERS - 1:
          currentTurn = 0
    print("Player {1} ({0}) eliminated, skipping turn...".format(name, idnum))

    # --- SEND NEXT TURN MESSAGE ---
    send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())

  # -- SKIP CURRENT IDNUM -- IF -> (1) It isn't their turn -> (2) They are a spectator --
  if idnum != started_idnums[currentTurn]:
    return

  # -- SKIP ELIMINATED PLAYERS --
  if idnum in eliminated_clients:
    currentTurn += 1
    if currentTurn > MAX_PLAYERS - 1:
          currentTurn = 0
    print("Player {1} ({0}) eliminated, skipping turn...".format(name, idnum))

    # --- SEND NEXT TURN MESSAGE ---
    send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())
    
    return


  # -- GAME COMPLETE -> START A NEW GAME --
  if len(eliminated_clients) == (MAX_PLAYERS-1):
    time.sleep(WON_DELAY_S)
    start_new_game()

    # sent by the player to put a tile onto the board (in all turns except
    # their second)
  if isinstance(msg, tiles.MessagePlaceTile):
    if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
      # notify client that placement was successful
      send_msg_all_clients(msg.pack())

      # check for token movement
      positionupdates, eliminated = board.do_player_movement(live_idnums)

      for msg in positionupdates:
        send_msg_all_clients(msg.pack())
      
      for idnum in eliminated:
        if idnum not in eliminated_clients:
          print("A player was eliminated!")
          eliminated_clients.append(idnum)
          send_msg_all_clients(tiles.MessagePlayerEliminated(idnum).pack())

      # pickup a new tile
      tileid = tiles.get_random_tileid()
      msg_specific_client(tiles.MessageAddTileToHand(tileid).pack(), started_idnums[currentTurn])

      # start next turn
      currentTurn += 1
      #back to first player
      # -------------- THIS NEEDS TO LATER BE CHANGED FROM 0 TO INITIAL PLAYER ---------------
      if currentTurn > MAX_PLAYERS - 1:
        currentTurn = 0
      send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())

  # sent by the player in the second turn, to choose their token's
  # starting path
  elif isinstance(msg, tiles.MessageMoveToken):
    if not board.have_player_position(msg.idnum):
      if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
        # check for token movement
        positionupdates, eliminated = board.do_player_movement(live_idnums)

        for msg in positionupdates:
          send_msg_all_clients(msg.pack())
        
        for idnum in eliminated:
          if idnum not in eliminated_clients:
            eliminated_clients.append(idnum)
            send_msg_all_clients(tiles.MessagePlayerEliminated(idnum).pack())
        
        # start next turn
        currentTurn += 1
        if currentTurn > MAX_PLAYERS - 1:
          currentTurn = 0
        send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())


def accept_new_client(socket, times_connected):
    global client_connections
    connection, address = socket.accept() # READ, SET IN SELECTOR BELOW
    client_connections.append([connection, times_connected])
    print("New connection accepted from {}, connection id: {}".format(address, times_connected))
    connection.setblocking(False) # NEED THIS OR SERVER HANGS
    data = types.SimpleNamespace(addr=address, idnum=times_connected)
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(connection, events, data=data)

def send_msg_all_clients(msg):
  global client_connections
  for client in client_connections:
    connection = client[0]
    connection.send(msg)

def msg_specific_client(msg, idnum):
  global client_connections
  for client in client_connections:
    if client[1] == idnum:
      client[0].send(msg)

def new_player_joined(name, idnum):

  global live_idnums

  # Add id check, use connections
  # Initiates a new player joining.
  if idnum not in live_idnums:
    live_idnums.append(idnum)
    # --- SEND A WELCOME MESSAGE ---
    msg_specific_client(tiles.MessageWelcome(idnum).pack(), idnum)
    
    # --- SEND PLAYER JOINED (ALL CLIENTS) ---
    if joined_msgs:
      for msg in joined_msgs:
        msg_specific_client(msg, idnum)
    send_msg_all_clients(tiles.MessagePlayerJoined(name, idnum).pack())
    joined_msgs.append(tiles.MessagePlayerJoined(name, idnum).pack())

    # --- SEND ALL MOVES UP TO THIS POINT ---
    


def start_new_game():

  global currentTurn
  global eliminated_clients
  global started_idnums
  global disconnected_count

  # reset globals
  disconnected_count = 0
  currentTurn = 0
  eliminated_clients = []
  board.reset()

  # --- SEND NEW GAME MESSAGE (ALL CLIENTS) ---
  send_msg_all_clients(tiles.MessageGameStart().pack())
  
  #  -------------------------------------------------------------------- Add check later in case people leave.
  # this, by definition, chooses random clients to play, and a random turn order.
  started_idnums = random.sample(live_idnums, MAX_PLAYERS)

  # --- SEND TILES TO (ACTIVE) CLIENTS ---
  for idnum in started_idnums:
        for _ in range(tiles.HAND_SIZE):
          tileid = tiles.get_random_tileid()
          msg_specific_client(tiles.MessageAddTileToHand(tileid).pack(), idnum)
  
  # --- SEND NEW TURN MESSAGE (ALL CLIENTS) ---
  send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())


#-------------------------------------------------- LEAVEING THEN JOINGING THEN LECINVG AIN .... MIGHT ISSUES
def receive_msg_client(key, mask, idnum):
  
  global live_idnums
  global client_connections
  global disconnected_count

  buffer = bytearray()
  connection = key.fileobj
  data = key.data

  if mask & selectors.EVENT_READ:
    try:
      chunk = connection.recv(4096)
    except:
      print("Connection to {} lost, closing connection.".format(data.addr))
      chunk = b''
    # can move turn/eliminated checks here to not save moves made by players
    # Eliminate if disconnected.
    if not chunk:
      print('Closing connection to', data.addr)
      sel.unregister(connection)
      connection.close()

      # DISCONNECT SPECIAL CONDITIONS

      # REMOVE FROM LIVEID LIST
      live_idnums.remove(idnum)
      # REMOVE FROM CONNECTIONS
      for client in client_connections:
        if client[1] == idnum:
          client_connections.remove(client)
      # ELIMINATE FROM GAME
      eliminated_clients.append(idnum)
      send_msg_all_clients(tiles.MessagePlayerEliminated(idnum).pack())
      # REMOVE FROM STARTED LIST


    buffer.extend(chunk)
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    print('received message {}'.format(msg))

    buffer = buffer[consumed:]
    return msg
  else:
    return False

  


# A list of tuples outlining the connections to the server
times_connected = 0

# create a TCP/IP socket
listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
HOSTNAME = ''
PORT_NUM = 30020
server_address = (HOSTNAME, PORT_NUM)
listen_sock.bind(server_address)

print('listening on {}'.format(listen_sock.getsockname()))

listen_sock.listen(32)
listen_sock.setblocking(False)

# selector usage
# this connects the selector with the listening socket
# data=None identifes the listening socket
sel.register(listen_sock, selectors.EVENT_READ, data=None)

while True:
    events = sel.select(timeout=None)
    for key, mask in events:
        if key.data is None: # Listening socket selector returns None, new client needs accepting.
            accept_new_client(key.fileobj, times_connected)
            times_connected += 1
        else:
            client_handler(key, mask) # A client socket which has already been accepted.