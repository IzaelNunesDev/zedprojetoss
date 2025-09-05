# Monster Coup Backend

This is the backend for the Monster Coup card game.

## Setup

1.  Create a virtual environment: `python3 -m venv venv`
2.  Activate it: `source venv/bin/activate`
3.  Install dependencies: `pip install -r requirements.txt`
4.  Run the server: `uvicorn app.main:app --reload`

## API Endpoints

### HTTP Endpoints

-   `POST /create-game`: Creates a new game and returns a `game_id`.
-   `POST /join-game/{game_id}/{player_id}`: Allows a player to join an existing game.

### WebSocket Endpoint

-   `WS /ws/{game_id}/{player_id}`: Establishes a WebSocket connection for real-time gameplay events.
