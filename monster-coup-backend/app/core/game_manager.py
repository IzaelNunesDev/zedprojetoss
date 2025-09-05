# app/core/game_manager.py
import uuid
from typing import Dict
from .models import Game

class GameManager:
    def __init__(self):
        self.active_games: Dict[str, Game] = {}

    def create_game(self) -> Game:
        game_id = str(uuid.uuid4())[:8] # Gera um ID único de 8 caracteres
        game = Game(game_id)
        self.active_games[game_id] = game
        return game

    def get_game(self, game_id: str) -> Game | None:
        return self.active_games.get(game_id)

# Instância global para ser usada no app
game_manager = GameManager()
