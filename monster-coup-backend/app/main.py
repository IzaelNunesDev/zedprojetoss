# app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List
import json

from .core.game_manager import game_manager
from .core.models import Player

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

    if player_id in game.players:
        raise HTTPException(status_code=400, detail="Player ID already exists in this game")

    player = Player(player_id)
    game.add_player(player)

    # Notifica todos os jogadores sobre o novo jogador
    await connection_manager.broadcast(game_id, {"type": "PLAYER_JOINED", "payload": game.get_public_state()})

    # Inicia o jogo se a sala estiver cheia (ex: 2 jogadores)
    if len(game.players) == 2:
        game.start_game()
        await connection_manager.broadcast(game_id, {"type": "GAME_START", "payload": game.get_public_state()})

    return {"message": f"Player {player_id} joined game {game_id}"}

@app.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    """
    Endpoint WebSocket para comunicação em tempo real durante o jogo.
    """
    game = game_manager.get_game(game_id)
    if not game or player_id not in game.players:
        await websocket.close(code=1008)
        return

    await connection_manager.connect(websocket, game_id)

    # Envia o estado atual para o jogador que acabou de se conectar
    await websocket.send_json({"type": "GAME_STATE", "payload": game.get_public_state()})

    try:
        while True:
            data = await websocket.receive_json()
            # Ex: {"type": "ACTION", "payload": {"action": "Treinar"}}

            # Valida se é a vez do jogador
            if game.current_turn_player_id == player_id:
                game.handle_action(player_id, data.get("payload"))

                # Após a ação, atualiza o estado para todos
                await connection_manager.broadcast(game_id, {"type": "GAME_STATE_UPDATE", "payload": game.get_public_state()})
            else:
                # Informa ao jogador que não é sua vez
                await websocket.send_json({"type": "ERROR", "message": "Not your turn"})

    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, game_id)
        # Opcional: Lógica para lidar com a desconexão de um jogador (pausar o jogo, etc.)
        await connection_manager.broadcast(game_id, {"type": "PLAYER_DISCONNECTED", "player_id": player_id})
