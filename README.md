# CITS3002-Simple-Game-Server

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