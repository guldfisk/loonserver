import hashlib
import time
import typing as t

import threading
import socket

from multiprocessing import Pipe, reduction

from throneloon.gamesession.gamesession import GameSession
from throneloon.io.interface import IOInterface
from throneloon.game.setup.setupinfo import SetupInfo

from loonserver.games.interface import SocketInterface
from loonserver.networking.jsonsocket import JsonSocket


class CreateGameException(Exception):
	pass


class LoonSession(GameSession):

	def __init__(
		self,
		connection,
		interface: IOInterface,
		player_ids: t.Iterable[str],
		setup_info: t.Optional[SetupInfo] = None,
		seed: t.Optional[t.ByteString] = None
	) -> None:
		super().__init__(connection, interface, setup_info, seed)

		self._player_ids = tuple(player_ids)

		self._accepting_new_connections = False #type: bool

	@property
	def player_ids(self) -> t.Tuple[str, ...]:
		return self._player_ids

	@property
	def interface(self) -> SocketInterface:
		return self._interface

	def _accept_connections(self):
		self._accepting_new_connections = True

		while self._accepting_new_connections:
			s = socket.fromfd(reduction.recv_handle(self._connection), socket.AF_INET, socket.SOCK_STREAM)
			player_id = self._connection.recv()
			self.interface.update_socket(player_id, JsonSocket(wrapping=s))

	def run(self):
		threading.Thread(target=self._accept_connections).start()
		super().run()


class LoonInstance(object):
	def __init__(
		self,
		player_ids: t.Iterable[str],
		setup_info: t.Optional[SetupInfo] = None,
		seed: t.Optional[t.ByteString] = None,
	) -> None:
		parent_end, child_end = Pipe()
		self._connection = parent_end

		self._session = LoonSession(
			connection = child_end,
			interface = SocketInterface(player_ids),
			player_ids = player_ids,
			setup_info = setup_info,
			seed = seed,
		)

	@property
	def connection(self):
		return self._connection

	@property
	def session(self) -> LoonSession:
		return self._session


class GameManager(object):

	def __init__(self, domain: str) -> None:
		self._domain = domain

		self._games = {} #type: t.Dict[str, LoonInstance]

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

	def create_game(
		self,
		game_id: str,
		setup_info: SetupInfo,
	) -> t.List[str]:

		if game_id in self._games:
			raise CreateGameException('Game already exists with ID {}'.format(game_id))

		player_ids = [self._get_player_id(game_id) for _ in range(setup_info.num_players)]

		self._games[game_id] = LoonInstance(
			player_ids = player_ids,
			setup_info = setup_info,
			seed = None,
		)

		self._games[game_id].session.start()

		return player_ids

	def player_id_registered(self, player_id: str) -> bool:
		return player_id in self._player_ids

	def new_connection(self, s: JsonSocket, player_id: str) -> bool:
		if player_id in self._player_ids:
			reduction.send_handle(
				self._games[self._player_ids[player_id]].connection,
				s.fileno(),
				self._games[self._player_ids[player_id]].session.pid,
			)
			self._games[self._player_ids[player_id]].connection.send(player_id)
			return True
		return False