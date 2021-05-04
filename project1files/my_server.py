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
# currentTurn = random.randint(0,MAX_PLAYERS)
start_game_flag = False
started_idnums = []
first_start = True
ig_welc_msgs = []
eliminated_clients = []


def client_handler(key, mask):

  data = key.data
  connection = key.fileobj
  host, port = data.addr
  name = '{}:{}'.format(host, port)
 
  # GLOBALS
  global start_game_flag
  global currentTurn
  global first_start
  global ig_welc_msgs
  global eliminated
  global started_idnums
  global eliminated_clients


  # Add id check, use connections
  # Initiates a new player joining.
  idnum = data.idnum
  if idnum not in live_idnums:
    live_idnums.append(idnum)
    # NOTIFY ALL PLAYERS, ANOTHER PLAYER JOINED
    if ig_welc_msgs:
      for msg in ig_welc_msgs:
        connection.send(msg)
    send_msg_all_clients(tiles.MessagePlayerJoined(name, idnum).pack())
    ig_welc_msgs.append(tiles.MessagePlayerJoined(name, idnum).pack())
    tiles.MessagePlayerJoined(name, idnum).pack()
    # After this connection, have enouph players joined?
    if len(live_idnums) >= MAX_PLAYERS:
      start_game_flag = True
    connection.send(tiles.MessageWelcome(idnum).pack())

  # If game is ready to start, start game for players, then reloop.
  if start_game_flag:
    if idnum not in started_idnums:
      connection.send(tiles.MessageGameStart().pack())
      started_idnums.append(idnum)

      for _ in range(tiles.HAND_SIZE):
        tileid = tiles.get_random_tileid()
        connection.send(tiles.MessageAddTileToHand(tileid).pack())

  if len(started_idnums) < MAX_PLAYERS: # do not move on until game is full.
    return

  # Once the game has begun, this is the point.
  if first_start:
    first_start = False
    send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())

  #if it ain't ur turn, NO ONE CARES .
  # or you are a spectator
  if not idnum == started_idnums[currentTurn]:
    return

  # no moves for you if you are eliminated,
  # move onto next non-eliminated player
  if idnum in eliminated_clients:
    currentTurn += 1
    print("Player {1} ({0}) eliminated, skipping turn...".format(name, idnum))
    send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())
    return


  # game over, time for round 2, or n+1...
  if len(eliminated_clients) == (MAX_PLAYERS-1):

    time.sleep(WON_DELAY_S)

    if idnum not in eliminated_clients:
      # GAME HAS BEEN WON, START A NEW SEQUENCE HERE.
      send_msg_all_clients(tiles.MessageGameStart().pack())
      # random new clients to play game, if more than max connections
      currentTurn = 0
      eliminated_clients = []
      if len(live_idnums) > MAX_PLAYERS:
        started_idnums = random.sample(live_idnums, MAX_PLAYERS)
      else:
        started_idnums = live_idnums.copy()

      for idnum in started_idnums:
        for _ in range(tiles.HAND_SIZE):
          tileid = tiles.get_random_tileid()
          msg_specific_client(tiles.MessageAddTileToHand(tileid).pack(), idnum)
      first_start = True
      board.reset()
      return

  

  buffer = bytearray()
  data = key.data

  if mask & selectors.EVENT_READ:
    chunk = connection.recv(4096)
    if not chunk:
      print('Closing connection to', data.addr)
      sel.unregister(connection)
      connection.close()

    buffer.extend(chunk)
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    print('received message {}'.format(msg))

    buffer = buffer[consumed:]

  

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
        connection.send(tiles.MessageAddTileToHand(tileid).pack())

        # start next turn
        currentTurn += 1
        #back to first player
        # -------------- THIS NEEDS TO LATER BE CHANGED FROM 0 TO INITIAL PLAYER ---------------
        if currentTurn > MAX_PLAYERS - 1:
          currentTurn = 0
        send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())
        # OLD
        # connection.send(tiles.MessagePlayerTurn(idnum).pack())

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
          # OLD
          # connection.send(tiles.MessagePlayerTurn(idnum).pack())


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