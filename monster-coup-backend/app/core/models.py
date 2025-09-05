# app/core/models.py

from uuid import uuid4
from random import shuffle
from typing import List, Dict

class Monster:
    def __init__(self, name: str, ability: str):
        self.name = name
        self.ability = ability

class Deck:
    def __init__(self):
        self.cards: List[Monster] = []
        monsters_data = [
            {"name": "Dragão", "ability": "Destruir um monstro do oponente."},
            {"name": "Espectro", "ability": "Roubar 2 moedas de um oponente."},
            {"name": "Falcão", "ability": "Trocar uma de suas cartas com uma do baralho."},
            {"name": "Golem", "ability": "Bloquear a ação 'Caçar' de outro jogador."},
            {"name": "Slime", "ability": "Pegar 3 moedas do banco."},
        ]
        # Cada monstro tem 3 cópias no baralho
        for monster_data in monsters_data:
            for _ in range(3):
                self.cards.append(Monster(name=monster_data["name"], ability=monster_data["ability"]))
        self.shuffle()

    def shuffle(self):
        shuffle(self.cards)

    def draw(self) -> Monster | None:
        if self.cards:
            return self.cards.pop()
        return None

class Player:
    def __init__(self, player_id: str):
        self.id = player_id
        self.monsters: List[Monster] = []
        self.coins = 2
        self.revealed_monsters: List[Monster] = []

    def lose_monster(self, monster_name: str):
        """Move um monstro da mão do jogador para a lista de revelados."""
        monster_to_reveal = next((m for m in self.monsters if m.name == monster_name), None)
        if monster_to_reveal:
            self.monsters.remove(monster_to_reveal)
            self.revealed_monsters.append(monster_to_reveal)
            print(f"Player {self.id} lost monster {monster_name}. Monsters left: {len(self.monsters)}")


class Game:
    def __init__(self, game_id: str):
        self.id = game_id
        self.players: Dict[str, Player] = {}
        self.deck = Deck()
        self.current_turn_player_id: str = None
        self.game_state: str = "WAITING_FOR_PLAYERS" # WAITING_FOR_PLAYERS, IN_PROGRESS, AWAITING_RESPONSE, FINISHED

        # Atributos para gerenciar ações e contestações
        self.pending_action: Dict | None = None

    def add_player(self, player_id: str) -> bool:
        if player_id not in self.players and len(self.players) < 2:
            self.players[player_id] = Player(player_id)
            return True
        return False

    def start_game(self):
        if len(self.players) == 2 and self.game_state == "WAITING_FOR_PLAYERS":
            for player in self.players.values():
                player.monsters.append(self.deck.draw())
                player.monsters.append(self.deck.draw())

            player_ids = list(self.players.keys())
            shuffle(player_ids)
            self.current_turn_player_id = player_ids[0]
            self.game_state = "IN_PROGRESS"
            print(f"Game {self.id} started. First turn: {self.current_turn_player_id}")

    def next_turn(self):
        player_ids = list(self.players.keys())
        current_index = player_ids.index(self.current_turn_player_id)
        next_index = (current_index + 1) % len(player_ids)
        self.current_turn_player_id = player_ids[next_index]
        print(f"Next turn: {self.current_turn_player_id}")

    def _check_for_winner(self):
        """Verifica se o jogo terminou."""
        active_players = [p for p in self.players.values() if len(p.monsters) > 0]
        if len(active_players) == 1:
            self.game_state = "FINISHED"
            # O payload do broadcast de fim de jogo pode incluir o ID do vencedor
            print(f"Game Over! Winner is {active_players[0].id}")

    def handle_action(self, player_id: str, action_data: dict):
        """Função "maestro" que recebe uma ação e a processa."""
        action_name = action_data.get("action")
        player = self.players[player_id]

        # --- Ações que não podem ser contestadas ---
        if action_name == "Treinar":
            player.coins += 1
            self.next_turn()
            return

        if action_name == "Caçar":
            player.coins += 2
            # Futuramente, aqui entraria a lógica de bloqueio do Golem
            self.next_turn()
            return

        if action_name == "Golpe Final":
            target_id = action_data.get("target_player_id")
            target_player = self.players.get(target_id)
            if player.coins >= 7 and target_player:
                player.coins -= 7
                # O cliente precisará enviar qual monstro o alvo escolheu perder
                # Simplificando por agora: perde o primeiro
                monster_to_lose = target_player.monsters[0]
                target_player.lose_monster(monster_to_lose.name)
                self._check_for_winner()
                self.next_turn()
            return

        # --- Ações de Monstro (que podem ser contestadas) ---
        # Em vez de executar, preparamos a ação e esperamos a resposta
        self.game_state = "AWAITING_RESPONSE"
        self.pending_action = {
            "action": action_name,
            "source_player_id": player_id,
            "target_player_id": action_data.get("target_player_id")
        }
        # O broadcast será feito no main.py para notificar sobre a ação declarada

    def resolve_pending_action(self, responding_player_id: str, contested: bool):
        """Resolve a ação pendente após a resposta do oponente."""
        if not self.pending_action:
            return

        source_player = self.players[self.pending_action["source_player_id"]]
        action_monster_name = self.pending_action["action"] # Ex: "Dragão"

        if not contested:
            # O oponente aceitou, a ação acontece
            self._execute_monster_ability(source_player, self.pending_action)
        else:
            # O oponente contestou! Hora da verdade.
            has_monster = any(m.name == action_monster_name for m in source_player.monsters)

            if has_monster:
                # O desafiante perdeu a contestação
                contestor = self.players[responding_player_id]
                monster_to_lose = contestor.monsters[0] # Simplificação
                contestor.lose_monster(monster_to_lose.name)

                # O jogador que provou ter a carta, troca-a por uma nova do baralho
                monster_to_swap = next(m for m in source_player.monsters if m.name == action_monster_name)
                source_player.monsters.remove(monster_to_swap)
                source_player.monsters.append(self.deck.draw())
                self.deck.cards.append(monster_to_swap) # Devolve a carta ao baralho
                self.deck.shuffle()

                # A ação original ainda acontece
                self._execute_monster_ability(source_player, self.pending_action)
            else:
                # O jogador que blefou foi pego e perde uma carta
                monster_to_lose = source_player.monsters[0] # Simplificação
                source_player.lose_monster(monster_to_lose.name)

        # Limpa a ação pendente e continua o jogo
        self.pending_action = None
        self.game_state = "IN_PROGRESS"
        self._check_for_winner()
        if self.game_state != "FINISHED":
            self.next_turn()

    def _execute_monster_ability(self, source_player: Player, action_data: dict):
        """Lógica interna para executar a habilidade de um monstro."""
        action_name = action_data["action"]
        target_player = self.players.get(action_data["target_player_id"])

        if action_name == "Dragão" and target_player:
            if target_player.monsters:
                monster_to_lose = target_player.monsters[0] # Simplificação
                target_player.lose_monster(monster_to_lose.name)

        elif action_name == "Espectro" and target_player:
            stolen_coins = min(target_player.coins, 2)
            target_player.coins -= stolen_coins
            source_player.coins += stolen_coins

        # Adicionar lógica para Falcão e Slime aqui...

    def get_private_state(self, player_id: str) -> dict:
        """Retorna o estado completo, incluindo as cartas ocultas de um jogador específico."""
        player = self.players.get(player_id)
        if not player:
            return {}

        public_state = self.get_public_state()
        public_state["my_monsters"] = [m.name for m in player.monsters]
        return public_state

    def get_public_state(self) -> dict:
        """Retorna um dicionário com o estado do jogo que é seguro para ser enviado a todos."""
        return {
            "id": self.id,
            "players": {
                p_id: {
                    "id": p.id,
                    "coins": p.coins,
                    "monsters_count": len(p.monsters),
                    "revealed_monsters": [m.name for m in p.revealed_monsters]
                }
                for p_id, p in self.players.items()
            },
            "current_turn_player_id": self.current_turn_player_id,
            "game_state": self.game_state,
            "deck_size": len(self.deck.cards),
            "pending_action": self.pending_action
        }
