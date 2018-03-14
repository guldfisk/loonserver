import hashlib
import time
import typing as t

from loonserver.games.socketjson import SocketInterface
from loonserver.networking.jsonsocket import JsonSocket
from throneloon.gamesession.gamesession import GameSession


class CreateGameException(Exception):
	pass


class LoonSession(GameSession):

	@property
	def interface(self) -> SocketInterface:
		return self._interface


class GameManager(object):

	def __init__(self) -> None:
		self._games = {} #type: t.Dict[str, LoonSession]

		self._player_ids = {} #type: t.Dict[str, str]

		self._hashing = hashlib.sha3_256()
		self._hashing.update(str(time.time()).encode('ASCII'))

	def _get_player_id(self, game_id: str):
		while True:
			self._hashing.update(str(time.time()).encode('ASCII'))
			_id = self._hashing.hexdigest()
			if not _id in self._player_ids:
				self._player_ids[_id] = game_id
				return _id

	def id_in_use(self, game_id: str) -> bool:
		return game_id in self._games

	def create_game(self, game_id: str) -> t.List[str]:
		if game_id in self._games:
			raise CreateGameException()
		player_ids = [self._get_player_id(game_id)]

		self._games[game_id] = LoonSession(SocketInterface(player_ids))

		self._games[game_id].start()

		return player_ids

	def player_id_registered(self, player_id: str) -> bool:
		return player_id in self._player_ids

	def new_connection(self, socket: JsonSocket, player_id: str) -> bool:
		if player_id in self._player_ids:
			self._games[self._player_ids[player_id]].interface.update_socket(player_id, socket)
			return True
		return False