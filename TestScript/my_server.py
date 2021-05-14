
# CITS3002 2021 (Semester 1) Assignment - Sockets.
# Jakub Wysocki [22716248]
# Code Tested on: Windows 10

"""
This server aims to create a connection between clients, and allow multiple clients to 
play a game of tiles with one another.

This version of the server implements all FOUR Tiers, as outlined in the project outline.
This functionality includes, but is not limited to:

- Being able to join in a currently in-progress game, and be 
send the neccesary data to be in time with the rest of the connected clients.
These clients will act as spectators, recieving all game-state data, and are able
to participate, potentially, in the next game.
- Client's are able to disconnect and be eliminted from the game,
 without disrupting game progress.
- If enough clients are connected then a new game is started; clients are given some time to reflect
after each game, specified in WON_DELAY_S.
- The server detects AFK players after AFK_TIMER seconds of inactivity and chooses a random move
to be played for them.

To start the server (on windows!) you can use the start_server.bat file.
To start a game client (again, windows!) you can use the start_game_client.bat file.
Otherwise, you are able to use   ~ python server.py  to start the server.

 * Additional Information will be outlined in the Project's Report, bundled with this file during submission.

"""


# IMPORTS
import socket
import sys
import tiles
import selectors
import types
import random
import time

# CONSTANTS
MAX_PLAYERS = tiles.PLAYER_LIMIT
WON_DELAY_S = 4 #seconds
AFK_TIMER =   3 #seconds
START_WAIT =  3 #seconds

# GLOBALS
sel =                   selectors.DefaultSelector()
board =                 tiles.Board()
currentTurn =           0
time_spent_afk =        0
wait_timer =            0
first_start =           True
first_turn =            True
first_timer =           True
force_start =           False
started_idnums =        []
live_idnums =           []
client_connections =    []
joined_msgs =           []  ## RESET AFTER LEAVING???
eliminated_clients =    []
disconnected_clients =  []
messages_sent =         []
player_hand_dict =      {}
afk_dict =              {}
id_game_state =         {}
# client crash problem

def client_handler(key, mask):
  """
  Once clients are accepted, this is where they will be handled.
  This function contains the majority of the server logic, and this
  is looped over all connected ID's constantly.

  It accepted the key, and the mask parameters which contain all that is needed
  to utilize the current socket belonging to the client which is being handled.

  This function does not return any meaningful objects, rather, return is used to
  break execution of this function to stop processing the current client.
  """

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
  global player_hand_dict
  global afk_dict
  global time_spent_afk
  global first_turn
  global id_game_state
  global wait_timer
  global force_start
  global first_timer

  # if a player leaves before every active player makes a turn, the client crashes...
  msg = receive_msg_client(key, mask, idnum)

  # --  NEW PLAYER JOINS --
  if idnum not in live_idnums:
    if idnum not in disconnected_clients:
      new_player_joined(name, idnum)
      # reset waiting timer
      first_timer = True

  # -- START FIRST GAME --
  if len(live_idnums) >= MAX_PLAYERS or force_start:
    if first_start:
      #reset globals
      first_start = False
      force_start = False
      first_timer = True
      wait_timer = 0
      #start game
      start_new_game()
  else:
    # - CANNOT CONTINUE UNLESS SUFFICIENT PLAYERS CONNECTED -
    if first_start:
      if first_timer:
        wait_timer = time.perf_counter()
        first_timer = False
      else:
        if (time.perf_counter() - wait_timer) >= START_WAIT:
          if len(live_idnums) > 1:
            force_start = True
      return
  
  # -- SKIP DISCONNECTED PLAYERS --
  if started_idnums[currentTurn] in disconnected_clients:
    currentTurn += 1
    if currentTurn > len(started_idnums) - 1:
          currentTurn = 0
    print("Player {1} ({0}) eliminated, skipping turn...".format(name, idnum))
    # --- SEND NEXT TURN MESSAGE ---
    send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())

  # -- SKIP CURRENT IDNUM -- IF -> (1) It isn't their turn -> (2) They are a spectator --
  if idnum != started_idnums[currentTurn]:
    return

  # -- GAME COMPLETE -> START A NEW GAME --
  if len(eliminated_clients) >= (len(started_idnums)-1):
    time.sleep(WON_DELAY_S)
    if len(live_idnums) < MAX_PLAYERS:
      started_idnums = []
      first_start = True
      return
    else:
      start_new_game()
      return

  # -- SKIP ELIMINATED PLAYERS --
  if idnum in eliminated_clients:
    currentTurn += 1
    if currentTurn > len(started_idnums) - 1:
          currentTurn = 0
    print("Player {1} ({0}) eliminated, skipping turn...".format(name, idnum))
    # --- SEND NEXT TURN MESSAGE ---
    send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())
    return

  # MAKE A VALID MOVE, BASED ON CLIENT MESSAGE,
  # OR A RANDOM MOVE FOR AFK PLAYERS
  # make_valid_move(started_idnums[currentTurn], msg, False) 

  # -- -- START AFK TIMER -- --
  if first_turn:
    first_turn = False
    afk_dict[started_idnums[currentTurn]] = time.perf_counter()

  if not msg:
    if started_idnums[currentTurn] not in afk_dict:
      return
    time_spent_afk += time.perf_counter() - afk_dict[started_idnums[currentTurn]]
    afk_dict[started_idnums[currentTurn]] = time.perf_counter()

    # AN AFK PLAYER IS MANAGED HERE
    if time_spent_afk >= AFK_TIMER:
      print("Player {}, ({}) AFK: Random Move.".format(idnum, name))
      time.sleep(1) # Give server time ------------------------------------------------------------- remove later
      if not first_start: # Check if game gas started
        time_spent_afk = 0
        first_turn = True
        make_valid_move(started_idnums[currentTurn], None, True)
    return
  else:
    time_spent_afk = 0
    if started_idnums[currentTurn] in afk_dict:
      afk_dict.pop(started_idnums[currentTurn])

  # AN AFK PLAYER SHOULDN'T GET HERE
  first_turn = True

  # -- -- END AFK TIMER -- --

  # MAKE A VALID MOVE, BASED ON CLIENT MESSAGE
  make_valid_move(started_idnums[currentTurn], msg, False)


def accept_new_client(socket, times_connected):
  """
  This is where new sockets are accepted and set up to be used be the client handler.
  This method uses the selector library to manage multiple connections.
  """
  global client_connections
  connection, address = socket.accept() # READ, SET IN SELECTOR BELOW
  client_connections.append([connection, times_connected])
  print("New connection accepted from {}, connection id: {}".format(address, times_connected))
  connection.setblocking(False) # NEED THIS OR SERVER HANGS
  data = types.SimpleNamespace(addr=address, idnum=times_connected)
  events = selectors.EVENT_READ | selectors.EVENT_WRITE
  sel.register(connection, events, data=data)

def send_msg_all_clients(msg):
  """
  This function sends out one message, msg, to all currently active connections.
  """
  global client_connections
  global messages_sent
  messages_sent.append(msg)
  for client in client_connections:
    client[0].send(msg)

def msg_specific_client(msg, idnum):
  """
  This function sends a message, msg, to a specific client, based on their idnum.
  """
  global client_connections
  for client in client_connections:
    if client[1] == idnum:
      client[0].send(msg)

def new_player_joined(name, idnum):
  """
  This function sets up a new client connecting, and joining a game.
  All clients join as effective "spectators", until a new game is begun.
  This function handles the delivery of the Welcome Message,
  and the delivery of the Player Joined Messages
  """
  global live_idnums
  global messages_sent
  global client_connections
  if idnum not in live_idnums:
    live_idnums.append(idnum)
    # --- SEND A WELCOME MESSAGE ---
    msg_specific_client(tiles.MessageWelcome(idnum).pack(), idnum)
    # --- SEND PLAYER JOINED (ALL CLIENTS, but this one) ---
    if joined_msgs:
      for msg in joined_msgs:
        msg_specific_client(msg, idnum)
    # To preserve Me! Message, send to all but this idnum
    for client in client_connections:
      if client[1] != idnum:
        client[0].send(tiles.MessagePlayerJoined(name, idnum).pack())
    messages_sent.append(tiles.MessagePlayerJoined(name, idnum).pack())
    joined_msgs.append(tiles.MessagePlayerJoined(name, idnum).pack())
    # --- SEND ALL MOVES UP TO THIS POINT ---
    if started_idnums:
      # Lot of stuff here is to make it work with the given tester
      for msg in messages_sent:
        test_msg, consumed = tiles.read_message_from_bytearray(msg)
        if not isinstance(test_msg, tiles.MessageGameStart):
          msg_specific_client(msg, idnum)


def start_new_game():
  """
  This void parameterless function, starts a new game for a randomly chosen selection of
  currently connected clients. It responsible for setting up global data and distributing 
  tiles to players.
  """

  global currentTurn
  global eliminated_clients
  global started_idnums
  global disconnected_count
  global messages_sent
  global board
  global player_hand_dict
  global afk_dict
  global id_game_state

  # reset globals
  disconnected_count =    0
  currentTurn =           0
  eliminated_clients =    []
  messages_sent =         []
  afk_dict =              {}
  player_hand_dict =      {}
  id_game_state =         {}
  board.reset()

  # --- SEND NEW GAME MESSAGE (ALL CLIENTS) ---
  send_msg_all_clients(tiles.MessageGameStart().pack())
  
  #  -------------------------------------------------------------------- Add check later in case people leave.
  # this, by definition, chooses random clients to play, and a random turn order.
  num_players = 4
  if len(live_idnums) < 4:
    num_players = len(live_idnums)
  started_idnums = random.sample(live_idnums, num_players)


  # --- SET ID GAME STATE ---
  for idnum in started_idnums:
    id_game_state[idnum] = ["first", []] 
    # [1] is last tile placement (x and y position)
    # [0] is defined as follows
    # "first" turn is a unique event.
    # "second" turn is a unique event.
    # "normal" (3 -> n) turn is a unique event.


  # --- SEND TILES TO (ACTIVE) CLIENTS ---
  for idnum in started_idnums:
    player_hand_dict[idnum] = []
    for _ in range(tiles.HAND_SIZE):
      tileid = tiles.get_random_tileid()
      player_hand_dict[idnum].append(tileid)
      msg_specific_client(tiles.MessageAddTileToHand(tileid).pack(), idnum)
  
  # --- SEND NEW TURN MESSAGE (ALL CLIENTS) ---
  send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())


#-------------------------------------------------- LEAVEING THEN JOINGING THEN LECINVG AIN .... MIGHT ISSUES
def receive_msg_client(key, mask, idnum):
  """
  This function is used to read information send by a client, using their
   established socket with the server. This function is called on every iteration
   of the client handler. 

   Players who disconnect are also managed in this function, and their relevant 
   information is changed here.

   When there is no data avalaible to read by the connection, this function will return False,
   otherwise, it will return the recieved message.
  """
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
      if idnum in started_idnums:
        if idnum not in eliminated_clients:
          eliminated_clients.append(idnum)
          # DO NOT ELIMINATE BEFORE FIRST TURN???!!!
          send_msg_all_clients(tiles.MessagePlayerEliminated(idnum).pack())
      disconnected_clients.append(idnum)
      #Remove from AFK DICT
      if idnum in afk_dict:
        afk_dict.pop(idnum)

    buffer.extend(chunk)
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    print('received message {}'.format(msg))
    buffer = buffer[consumed:]
    return msg
  else:
    return False

def make_valid_move(idnum, msg, is_random):
  """In this function we will attempt to make a valid move for the given idnum,
  this is regardless if its a tile move or a token move.  There is also an option
  to generate a random move, without using the given message field.

  The random move is used for player who have been AFK for over
  AFK TIMER seconds. For this use case, use None for a msg value.
  For a random move, is_random should be set to True, False otherwise.
  """
  global started_idnums
  global eliminated_clients
  global player_hand_dict
  global live_idnums
  global currentTurn
  global id_game_state
  
  move_found = False
  random_tile = False
  random_token = False

  # - FOR RANDOM TILE MOVMENT
  # all current tileids in hand
  hand = player_hand_dict[started_idnums[currentTurn]].copy()
  # all possible rotation values
  r_val = list(range(0, 4))
  # all possible x values
  x_pos = list(range(0, tiles.BOARD_WIDTH))
  # all possible y values
  y_pos = list(range(0, tiles.BOARD_HEIGHT))
  # Ensure that moves are random.
  random.shuffle(x_pos)
  random.shuffle(y_pos)
  random.shuffle(r_val)
  random.shuffle(hand)

  # - FOR RANDOM TOKEN MOVMENT
  # all possible token locations, randomized
  t_pos = list(range(0, 8))
  random.shuffle(t_pos)
  
  # This uses a brute force method to find a valid tile, will run slower on
  # larger boards. There is a possibility of using inbuilt ig_game_state to make
  # smarter decisions if required.
  if is_random:
    ### FOR FIRST TURN ###
    if id_game_state[started_idnums[currentTurn]][0] == "first":
      # chooses a random spot on edge of board to play.
      for x in x_pos:
        for y in y_pos:
          for r in r_val:
            for tileid in hand:
              if not move_found:
                if board.set_tile(x, y, tileid, r, idnum):
                  msg = tiles.MessagePlaceTile(idnum, tileid, r, x, y)
                  move_found = True
                  random_tile = True

    ### FOR TOKEN MOVEMENTS ###
    if id_game_state[started_idnums[currentTurn]][0] == "second":
      # choose a random token position to play.
      for x in x_pos:
        for y in y_pos:
          for t in t_pos:
            if not move_found:
              if board.set_player_start_position(idnum, x, y, t):
                msg = tiles.MessageMoveToken(idnum, x, y, t)
                move_found = True
                random_token = True

    ### FOR NORMAL TILE MOVMENT ###
    if id_game_state[started_idnums[currentTurn]][0] == "normal":
      # chooses a random spot on board to play.
      for x in x_pos:
        for y in y_pos:
          for r in r_val:
            for tileid in hand:
              if not move_found:
                if board.set_tile(x, y, tileid, r, idnum):
                  msg = tiles.MessagePlaceTile(idnum, tileid, r, x, y)
                  move_found = True
                  random_tile = True

  # ---- NEXT TURN BEGINS HERE ----
  # sent by the player to put a tile onto the board (in all turns except
  # their second)
  if isinstance(msg, tiles.MessagePlaceTile):
    #This checks if the player has this tile in their hand -- FAIR PLAY, CHECK HAND.
    if msg.tileid not in player_hand_dict[started_idnums[currentTurn]]:
      print("Player {0} attempted to play a tile, {1}, not in their hand: {2}.".format(idnum, msg.tileid, player_hand_dict[started_idnums[currentTurn]]))
      return
    if random_tile or board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
      # notify client that placement was successful
      send_msg_all_clients(msg.pack())

      # check for token movement
      check_ids = []
      for started_idnum in started_idnums:
        if started_idnum not in eliminated_clients:
          check_ids.append(started_idnum)

      positionupdates, eliminated = board.do_player_movement(check_ids)

      # pickup a new tile, update hand dictionary
      player_hand_dict[started_idnums[currentTurn]].remove(msg.tileid)
      tileid = tiles.get_random_tileid()
      msg_specific_client(tiles.MessageAddTileToHand(tileid).pack(), started_idnums[currentTurn])
      player_hand_dict[started_idnums[currentTurn]].append(tileid)

      #update current id's game state
      if id_game_state[started_idnums[currentTurn]][0] == "first":
        id_game_state[started_idnums[currentTurn]][0] = "second"

      for msg in positionupdates: # - --------------------------------------------------------------------------------------------- eliminated tokens move, fix maybe???
        send_msg_all_clients(msg.pack())
      
      for idnum in eliminated:
        if idnum not in eliminated_clients:
          print("player {} was eliminated!".format(idnum))
          eliminated_clients.append(idnum)
          send_msg_all_clients(tiles.MessagePlayerEliminated(idnum).pack())

      # start next turn
      currentTurn += 1
      if currentTurn > len(started_idnums) - 1:
        currentTurn = 0
      send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())

  # sent by the player in the second turn, to choose their token's
  # starting path
  elif isinstance(msg, tiles.MessageMoveToken):
    if not board.have_player_position(msg.idnum) or random_token:
      if random_token or board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):

        # check for token movement
        check_ids = []
        for started_idnum in started_idnums:
          if started_idnum not in eliminated_clients:
            check_ids.append(started_idnum)
        positionupdates, eliminated = board.do_player_movement(check_ids)

        if id_game_state[started_idnums[currentTurn]][0] == "second":
          id_game_state[started_idnums[currentTurn]][0] = "normal"  

        for msg in positionupdates:
          send_msg_all_clients(msg.pack())
        
        for idnum in eliminated:
          if idnum not in eliminated_clients:
            print("player {} was eliminated!".format(idnum))
            eliminated_clients.append(idnum)
            send_msg_all_clients(tiles.MessagePlayerEliminated(idnum).pack())
        
        # start next turn
        currentTurn += 1
        if currentTurn > len(started_idnums) - 1:
          currentTurn = 0
        send_msg_all_clients(tiles.MessagePlayerTurn(started_idnums[currentTurn]).pack())
  return


#                                                #
# This is where the programs "execution" begins. #
#                                                #

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