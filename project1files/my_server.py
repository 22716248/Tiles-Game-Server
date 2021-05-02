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
from random import randint

MAX_PLAYERS = 2

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


def client_handler(key, mask):

  data = key.data
  connection = key.fileobj
  host, port = data.addr
  name = '{}:{}'.format(host, port)

  # GLOBALS
  global start_game_flag
  global currentTurn
  global first_start


  # Add id check, use connections
  # Initiates a new player joining.
  idnum = data.idnum
  if idnum not in live_idnums:
    live_idnums.append(idnum)
    # NOTIFY ALL PLAYERS, ANOTHER PLAYER JOINED
    send_msg_all_clients(tiles.MessagePlayerJoined(name, idnum).pack())
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
    all_message = tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack()
    send_to_all = live_idnums.copy()

  #if it ain't ur turn, NO ONE CARES .
  if not idnum == started_idnums[currentTurn]:
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
        connection.send(msg.pack())

        # check for token movement
        positionupdates, eliminated = board.do_player_movement(live_idnums)

        for msg in positionupdates:
          connection.send(msg.pack())
        
        if idnum in eliminated:
          connection.send(tiles.MessagePlayerEliminated(idnum).pack())
          return

        # pickup a new tile
        tileid = tiles.get_random_tileid()
        connection.send(tiles.MessageAddTileToHand(tileid).pack())

        # start next turn
        currentTurn += 1
        #back to first player
        # -------------- THIS NEEDS TO LATER BE CHANGED FROM 0 TO INITIAL PLAYER ---------------
        if currentTurn > MAX_PLAYERS:
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
            connection.send(msg.pack())
          
          if idnum in eliminated:
            connection.send(tiles.MessagePlayerEliminated(idnum).pack())
            return
          
          # start next turn
          currentTurn += 1
          # OLD
          # connection.send(tiles.MessagePlayerTurn(idnum).pack())


def accept_new_client(socket, times_connected):
    global client_connections
    connection, address = socket.accept() # READ, SET IN SELECTOR BELOW
    client_connections.append(connection)
    print("New connection accepted from {}, connection id: {}".format(address, times_connected))
    connection.setblocking(False) # NEED THIS OR SERVER HANGS
    data = types.SimpleNamespace(addr=address, idnum=times_connected)
    events = selectors.EVENT_READ | selectors.EVENT_WRITE
    sel.register(connection, events, data=data)


def send_msg_all_clients(msg):
  global client_connections
  for conn in client_connections:
    conn.send(msg)


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

listen_sock.listen(16)
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
            if all_msg:
              send_msg_to_all(key, mask)
            else:
              client_handler(key, mask) # A client socket which has already been accepted.