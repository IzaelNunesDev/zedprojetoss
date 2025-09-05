# app/main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from typing import Dict, List
import logging

from .core.game_manager import game_manager

# Configuração de logging para depuração
logging.basicConfig(level=logging.INFO)

app = FastAPI()

class ConnectionManager:
    ### MUDANÇA: Estrutura para associar websocket ao player_id dentro de um jogo.
    # Isso facilita o envio de mensagens privadas e o gerenciamento de reconexões.
    def __init__(self):
        self.active_connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, game_id: str, player_id: str):
        await websocket.accept()
        if game_id not in self.active_connections:
            self.active_connections[game_id] = {}
        self.active_connections[game_id][player_id] = websocket
        logging.info(f"Player {player_id} connected to game {game_id}")

    def disconnect(self, game_id: str, player_id: str):
        if game_id in self.active_connections and player_id in self.active_connections[game_id]:
            del self.active_connections[game_id][player_id]
            logging.info(f"Player {player_id} disconnected from game {game_id}")

    async def broadcast(self, game_id: str, message: dict):
        if game_id in self.active_connections:
            for player_id, connection in self.active_connections[game_id].items():
                await connection.send_json(message)

    ### MUDANÇA: Função para enviar uma mensagem para um jogador específico.
    async def send_to_player(self, game_id: str, player_id: str, message: dict):
        if game_id in self.active_connections and player_id in self.active_connections[game_id]:
            await self.active_connections[game_id][player_id].send_json(message)


connection_manager = ConnectionManager()

@app.post("/create-game")
async def handle_create_game():
    game = game_manager.create_game()
    return {"game_id": game.id}

@app.post("/join-game/{game_id}/{player_id}")
async def handle_join_game(game_id: str, player_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.game_state.value != "WAITING_FOR_PLAYERS":
        raise HTTPException(status_code=400, detail="Game has already started")

    ### MUDANÇA: Lógica de adicionar jogador simplificada para corresponder a models.py
    if not game.add_player(player_id):
        raise HTTPException(status_code=400, detail="Player ID already exists or game is full.")

    await connection_manager.broadcast(game_id, {"type": "PLAYER_JOINED", "payload": game.get_public_state()})

    if len(game.players) == 2: # Define o número de jogadores para iniciar
        game.start_game()
        await connection_manager.broadcast(game_id, {"type": "GAME_START", "payload": game.get_public_state()})

    return {"message": f"Player {player_id} joined game {game_id}"}


@app.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    game = game_manager.get_game(game_id)
    if not game or player_id not in game.players:
        await websocket.close(code=1008)
        return

    await connection_manager.connect(websocket, game_id, player_id)
    # Envia o estado privado inicial
    await connection_manager.send_to_player(game_id, player_id, {"type": "PRIVATE_STATE", "payload": game.get_private_state(player_id)})

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            payload = data.get("payload")

            if message_type == "PLAYER_ACTION" and game.current_turn_player_id == player_id:
                game.handle_action(player_id, payload)

            elif message_type == "ACTION_RESPONSE":
                game.resolve_pending_action(player_id, payload.get("contested", False))

            ### MUDANÇA: Novo tipo de mensagem para quando um jogador escolhe uma carta
            elif message_type == "CHOOSE_MONSTER" and game.player_to_choose == player_id:
                game.handle_player_choice(player_id, payload.get("monster_name"))

            else:
                await connection_manager.send_to_player(game_id, player_id, {"type": "ERROR", "message": "Invalid action or not your turn."})
                continue # Pula o broadcast se a ação for inválida

            # Após qualquer ação válida, notifica todos sobre o novo estado
            await connection_manager.broadcast(game_id, {"type": "GAME_STATE_UPDATE", "payload": game.get_public_state()})

            # Envia estado privado atualizado para cada jogador
            for pid in game.players:
                await connection_manager.send_to_player(game_id, pid, {"type": "PRIVATE_STATE", "payload": game.get_private_state(pid)})


    except WebSocketDisconnect:
        connection_manager.disconnect(game_id, player_id)
        await connection_manager.broadcast(game_id, {"type": "PLAYER_DISCONNECTED", "player_id": player_id})
