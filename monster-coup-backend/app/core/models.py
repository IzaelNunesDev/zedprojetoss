# app/core/models.py
import random
from typing import List, Dict
from enum import Enum

### MUDANÇA: Usando Enum para estados de jogo mais seguros.
class GameState(str, Enum):
    WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_RESPONSE = "AWAITING_RESPONSE"
    AWAITING_CHOICE = "AWAITING_CHOICE" # Estado para esperar a escolha do jogador
    FINISHED = "FINISHED"

class Monster:
    def __init__(self, name: str, ability: str):
        self.name = name
        self.ability_description = ability

class Deck:
    def __init__(self):
        self.cards: List[Monster] = self._create_deck()
        self.shuffle()

    def _create_deck(self) -> List[Monster]:
        monsters_data = {
            "Dragão": "Destruir um monstro do oponente.",
            "Espectro": "Roubar 2 moedas de um oponente.",
            "Falcão": "Trocar uma de suas cartas com uma do baralho.",
            "Golem": "Bloquear a ação 'Caçar' de outro jogador.",
            "Slime": "Pegar 3 moedas do banco.",
        }
        deck = []
        for name, ability in monsters_data.items():
            deck.extend([Monster(name, ability)] * 3)
        return deck

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self) -> Monster | None:
        return self.cards.pop() if self.cards else None

class Player:
    def __init__(self, player_id: str):
        self.id = player_id
        self.monsters: List[Monster] = []
        self.coins = 2
        self.revealed_monsters: List[Monster] = []

    def lose_monster(self, monster_name: str) -> bool:
        monster_to_reveal = next((m for m in self.monsters if m.name == monster_name), None)
        if monster_to_reveal:
            self.monsters.remove(monster_to_reveal)
            self.revealed_monsters.append(monster_to_reveal)
            return True
        return False

class Game:
    def __init__(self, game_id: str):
        self.id = game_id
        self.players: Dict[str, Player] = {}
        self.deck = Deck()
        self.current_turn_player_id: str = None
        self.game_state: GameState = GameState.WAITING_FOR_PLAYERS

        self.pending_action: Dict | None = None
        ### MUDANÇA: Atributo para guardar quem precisa fazer uma escolha.
        self.player_to_choose: str | None = None

    def add_player(self, player_id: str) -> bool:
        if player_id not in self.players and len(self.players) < 2:
            player = Player(player_id)
            self.players[player_id] = player
            return True
        return False

    def start_game(self):
        if len(self.players) == 2 and self.game_state == GameState.WAITING_FOR_PLAYERS:
            for player in self.players.values():
                player.monsters.append(self.deck.draw())
                player.monsters.append(self.deck.draw())
            player_ids = list(self.players.keys())
            random.shuffle(player_ids)
            self.current_turn_player_id = player_ids[0]
            self.game_state = GameState.IN_PROGRESS

    def next_turn(self):
        player_ids = list(self.players.keys())
        # Garante que apenas jogadores com monstros restantes possam jogar
        active_player_ids = [pid for pid, p in self.players.items() if len(p.monsters) > 0]
        if not active_player_ids or self.current_turn_player_id not in active_player_ids:
             self._check_for_winner()
             return

        current_index = active_player_ids.index(self.current_turn_player_id)
        next_index = (current_index + 1) % len(active_player_ids)
        self.current_turn_player_id = active_player_ids[next_index]

    def _check_for_winner(self):
        active_players = [p for p in self.players.values() if len(p.monsters) > 0]
        if len(active_players) <= 1:
            self.game_state = GameState.FINISHED
            print(f"Game Over! Winner is {active_players[0].id if active_players else 'None'}")

    def handle_action(self, player_id: str, action_data: dict):
        action_name = action_data.get("action")
        player = self.players[player_id]

        # Ações que não podem ser contestadas
        if action_name in ["Treinar", "Caçar"]:
            if action_name == "Treinar": player.coins += 1
            if action_name == "Caçar": player.coins += 2
            self.next_turn()
            return

        if action_name == "Golpe Final":
            target_id = action_data.get("target_player_id")
            if player.coins >= 7 and target_id in self.players:
                player.coins -= 7
                self.game_state = GameState.AWAITING_CHOICE
                self.player_to_choose = target_id
                # O broadcast no main.py irá notificar o alvo para escolher
            return

        # Ações de Monstro (que podem ser contestadas)
        self.game_state = GameState.AWAITING_RESPONSE
        self.pending_action = {
            "action": action_name,
            "source_player_id": player_id,
            "target_player_id": action_data.get("target_player_id")
        }

    def resolve_pending_action(self, responding_player_id: str, contested: bool):
        if not self.pending_action: return

        source_player = self.players[self.pending_action["source_player_id"]]
        action_monster = self.pending_action["action"]

        if not contested:
            self._execute_monster_ability(source_player, self.pending_action)
        else:
            has_monster = any(m.name == action_monster for m in source_player.monsters)
            if has_monster:
                # O contestador perdeu, precisa escolher uma carta para perder
                self.game_state = GameState.AWAITING_CHOICE
                self.player_to_choose = responding_player_id
                # Troca a carta do jogador que provou
                monster_to_swap = next(m for m in source_player.monsters if m.name == action_monster)
                source_player.monsters.remove(monster_to_swap)
                new_card = self.deck.draw()
                if new_card: source_player.monsters.append(new_card)
                self.deck.cards.append(monster_to_swap)
                self.deck.shuffle()
                # A ação original ainda acontece depois que o contestador perder a carta
            else:
                # O blefador foi pego, precisa escolher uma carta para perder
                self.game_state = GameState.AWAITING_CHOICE
                self.player_to_choose = source_player.id
                # A ação é cancelada
                self.pending_action = None

    ### MUDANÇA: Nova função para lidar com a escolha de uma carta
    def handle_player_choice(self, player_id: str, monster_name: str):
        if self.game_state != GameState.AWAITING_CHOICE or self.player_to_choose != player_id:
            return

        player = self.players[player_id]
        player.lose_monster(monster_name)

        # Se a escolha foi resultado de uma contestação ganha, a ação original acontece agora
        if self.pending_action:
             source_player = self.players[self.pending_action["source_player_id"]]
             self._execute_monster_ability(source_player, self.pending_action)

        self.pending_action = None
        self.player_to_choose = None
        self.game_state = GameState.IN_PROGRESS
        self._check_for_winner()
        if self.game_state != GameState.FINISHED:
            self.next_turn()

    def _execute_monster_ability(self, source_player: Player, action_data: dict):
        action = action_data["action"]
        target_id = action_data.get("target_player_id")

        if action == "Dragão" and target_id:
            self.game_state = GameState.AWAITING_CHOICE
            self.player_to_choose = target_id
        elif action == "Espectro" and target_id:
            target = self.players[target_id]
            stolen = min(target.coins, 2)
            target.coins -= stolen
            source_player.coins += stolen
        elif action == "Slime":
            source_player.coins += 3
        elif action == "Falcão":
            # Simplificação: troca a primeira carta do jogador.
            if source_player.monsters:
                card_to_swap = source_player.monsters[0]
                source_player.monsters.remove(card_to_swap)
                new_card = self.deck.draw()
                if new_card:
                    source_player.monsters.append(new_card)
                self.deck.cards.append(card_to_swap)
                self.deck.shuffle()
        # A habilidade do Golem (bloqueio) é reativa e precisa de uma mudança
        # na arquitetura para ser implementada, tratando de respostas a ações.

    def get_private_state(self, player_id: str) -> dict:
        player = self.players.get(player_id)
        if not player: return {}
        state = self.get_public_state()
        state["my_monsters"] = [m.name for m in player.monsters]
        return state

    def get_public_state(self) -> dict:
        return {
            "id": self.id,
            "players": {
                p_id: {
                    "id": p.id,
                    "coins": p.coins,
                    "monsters_count": len(p.monsters),
                    "revealed_monsters": [m.name for m in p.revealed_monsters]
                } for p_id, p in self.players.items()
            },
            "current_turn_player_id": self.current_turn_player_id,
            "game_state": self.game_state.value, # Envia o valor da string do Enum
            "deck_size": len(self.deck.cards),
            "pending_action": self.pending_action,
            "player_to_choose": self.player_to_choose
        }
