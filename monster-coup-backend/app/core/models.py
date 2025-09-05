# app/core/models.py
import random
from typing import List, Dict

# Classe base para os monstros, facilitando a criação do baralho
class Monster:
    def __init__(self, name: str, ability: str):
        self.name = name
        self.ability_description = ability

# Classe que gerencia o baralho de cartas
class Deck:
    def __init__(self):
        self.cards: List[Monster] = self._create_deck()
        self.shuffle()

    def _create_deck(self) -> List[Monster]:
        monsters_data = {
            "Dragão": "Força oponente a perder 1 monstro.",
            "Slime": "Recupera 1 monstro eliminado.",
            "Golem": "Bloqueia o ataque do Dragão.",
            "Espectro": "Rouba 2 moedas de um oponente.",
            "Falcão": "Espia 1 monstro do oponente."
        }
        deck = []
        for name, ability in monsters_data.items():
            deck.extend([Monster(name, ability)] * 3) # 3 cópias de cada
        return deck

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self) -> Monster:
        return self.cards.pop() if self.cards else None

# Classe que representa um jogador
class Player:
    def __init__(self, player_id: str):
        self.id = player_id
        self.coins = 2
        self.monsters: List[Monster] = []
        self.revealed_monsters: List[Monster] = [] # Cemitério

    def lose_monster(self, monster_name: str) -> bool:
        monster_to_remove = next((m for m in self.monsters if m.name == monster_name), None)
        if monster_to_remove:
            self.monsters.remove(monster_to_remove)
            self.revealed_monsters.append(monster_to_remove)
            return True
        return False

# Classe principal que orquestra o jogo
class Game:
    def __init__(self, game_id: str):
        self.id = game_id
        self.players: Dict[str, Player] = {}
        self.deck = Deck()
        self.current_turn_player_id: str = None
        self.game_state: str = "WAITING_FOR_PLAYERS" # Outros estados: IN_PROGRESS, FINISHED
        # ... outros atributos como histórico de ações, ação pendente de contestação, etc.

    def add_player(self, player: Player):
        # Adiciona um jogador e distribui suas cartas iniciais
        if len(self.players) < 4: # Limite de jogadores
            player.monsters.append(self.deck.draw())
            player.monsters.append(self.deck.draw())
            self.players[player.id] = player

    def start_game(self):
        # Define o primeiro jogador e muda o estado do jogo
        self.current_turn_player_id = list(self.players.keys())[0]
        self.game_state = "IN_PROGRESS"

    def next_turn(self):
        player_ids = list(self.players.keys())
        current_index = player_ids.index(self.current_turn_player_id)
        next_index = (current_index + 1) % len(player_ids)
        self.current_turn_player_id = player_ids[next_index]

    def handle_action(self, player_id: str, action_data: dict):
        # Função "maestro" que recebe uma ação e a processa
        # Ex: action_data = {"action": "Treinar"}
        # Ex: action_data = {"action": "Dragao", "target": "player2"}
        pass

    def get_public_state(self) -> dict:
        return {
            "game_id": self.id,
            "game_state": self.game_state,
            "current_turn_player_id": self.current_turn_player_id,
            "players": {
                p_id: {
                    "coins": p.coins,
                    "revealed_monsters": [m.name for m in p.revealed_monsters],
                    "monsters_count": len(p.monsters)
                }
                for p_id, p in self.players.items()
            }
        }
