# app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List
import json

from .core.game_manager import game_manager


app = FastAPI()

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_id: str):
        await websocket.accept()
        if game_id not in self.active_connections:
            self.active_connections[game_id] = []
        self.active_connections[game_id].append(websocket)

    def disconnect(self, websocket: WebSocket, game_id: str):
        if game_id in self.active_connections:
            self.active_connections[game_id].remove(websocket)

    async def broadcast(self, game_id: str, message: dict):
        if game_id in self.active_connections:
            for connection in self.active_connections[game_id]:
                await connection.send_json(message)

connection_manager = ConnectionManager()

@app.post("/create-game")
async def handle_create_game():
    """
    Cria um novo jogo e retorna seu ID.
    """
    game = game_manager.create_game()
    return {"game_id": game.id}

@app.post("/join-game/{game_id}/{player_id}")
async def handle_join_game(game_id: str, player_id: str):
    """
    Permite que um jogador entre em um jogo existente.
    """
    game = game_manager.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if game.game_state != "WAITING_FOR_PLAYERS":
        raise HTTPException(status_code=400, detail="Game has already started")

    if not game.add_player(player_id):
        raise HTTPException(status_code=400, detail="Player ID already exists in this game or game is full.")

    # Notifica todos os jogadores sobre o novo jogador
    await connection_manager.broadcast(game_id, {"type": "PLAYER_JOINED", "payload": game.get_public_state()})

    # Inicia o jogo se a sala estiver cheia (ex: 2 jogadores)
    if len(game.players) == 2:
        game.start_game()
        await connection_manager.broadcast(game_id, {"type": "GAME_START", "payload": game.get_public_state()})

    return {"message": f"Player {player_id} joined game {game_id}"}

@app.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    game = game_manager.get_game(game_id)
    if not game or player_id not in game.players:
        await websocket.close(code=1008)
        return

    await connection_manager.connect(websocket, game_id)

    # Envia o estado privado para o jogador que acabou de se conectar
    await websocket.send_json({"type": "PRIVATE_STATE", "payload": game.get_private_state(player_id)})

    try:
        while True:
            data = await websocket.receive_json()
            # Ex: {"type": "PLAYER_ACTION", "payload": {"action": "Dragão", "target_player_id": "p2"}}
            # Ex: {"type": "ACTION_RESPONSE", "payload": {"contest": true}}

            message_type = data.get("type")
            payload = data.get("payload")

            if message_type == "PLAYER_ACTION" and game.current_turn_player_id == player_id:
                game.handle_action(player_id, payload)

                if game.game_state == "AWAITING_RESPONSE":
                    # Notifica todos que uma ação foi declarada
                    await connection_manager.broadcast(game_id, {"type": "ACTION_DECLARED", "payload": game.pending_action})
                else:
                    # Ação foi resolvida instantaneamente (Treinar, etc)
                    await connection_manager.broadcast(game_id, {"type": "GAME_STATE_UPDATE", "payload": game.get_public_state()})

            elif message_type == "ACTION_RESPONSE":
                # Um jogador está respondendo a uma ação (contestando ou não)
                game.resolve_pending_action(player_id, payload.get("contested", False))

                if game.game_state == "FINISHED":
                     await connection_manager.broadcast(game_id, {"type": "GAME_OVER", "payload": game.get_public_state()})
                else:
                     await connection_manager.broadcast(game_id, {"type": "GAME_STATE_UPDATE", "payload": game.get_public_state()})

            else:
                await websocket.send_json({"type": "ERROR", "message": "Invalid action or not your turn."})

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, game_id)
        await connection_manager.broadcast(game_id, {"type": "PLAYER_DISCONNECTED", "player_id": player_id})
