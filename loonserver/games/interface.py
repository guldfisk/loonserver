import typing as t

import re
import threading

from eventtree.replaceevent import Event, Condition

from throneloon.game.artifacts.players import Player
from throneloon.game.artifacts.artifact import GameArtifact
from throneloon.game.artifacts.observation import GameObserver
from throneloon.game.artifacts.artifact import GameObject
from throneloon.io.interface import IOInterface, io_additional_options, io_option, io_options

from loonserver.networking.jsonsocket import JsonSocket


def _stringify_option(option: io_option):
	if isinstance(option, GameArtifact):
		return option.name
	elif isinstance(option, Condition):
		return option.source.name
	else:
		return option


def _jsonify_game_object(game_object: GameObject, player: GameObserver) -> t.Any:
	return {
		key: (
			value.serialize(player).get('id', None)
			if isinstance(value, GameObject) else
			value
		) for key, value in game_object.serialize(player).items()
	}


def _jsonify_condition(condition: Condition, player: GameObserver) -> t.Any:
	return {
		'type': 'condition',
		'source': _jsonify(condition.source, player)
	}


def _jsonify(option: io_option, player: GameObserver) -> t.Any:
	if isinstance(option, GameObject):
		return _jsonify_game_object(option, player)
	elif isinstance(option, Condition):
		return _jsonify_condition(option, player)
	elif isinstance(option, str):
		return option
	elif isinstance(option, type):
		return type.__name__
	else:
		return str(option)


class SelectionException(Exception):
	pass


class BinaryLock(object):

	def __init__(self):
		super().__init__()
		self._locked = False
		self._lock = threading.Lock()

	def acquire(self):
		self._locked = True
		self._lock.acquire()

	def release(self):
		if not self._locked:
			return
		self._locked = False
		self._lock.release()


class PlayerConnection(object):

	def __init__(self, player: t.Optional[Player] = None, socket: t.Optional[JsonSocket] = None):
		self.player = player #type: t.Optional[Player]
		self._socket = socket #type: t.Optional[JsonSocket]
		self.events = [] #type: t.List[t.Tuple[Event, bool]]
		self._pending_selection = None #type: t.Any

		self._lock = BinaryLock()
		self._lock.acquire()

		self._returned_json = None

	def _ask_player(self, options: t.Any):
		self._socket.send_json(options)
		self._returned_json = self._socket.get_json()
		self._lock.release()

	def _notify_event(self, event: Event, first: bool):
		self._socket.send_json(
			{
				'type': 'event',
				'event_type': event.__class__.__name__,
				'first': first,
				'values': dict({key: _jsonify(value, self.player) for key, value in event.values.items()}),
			}
		)

	def _select(self) -> str:
		self._ask_player(self._pending_selection)

		self._pending_selection = None

		_res = self._returned_json

		if (
			not isinstance(_res, dict)
			or not _res.get('type', None) == 'option_response'
			or not isinstance(_res.get('selected', None), str)
		):
			raise SelectionException()

		return self._returned_json['selected']

	def select(self, options: t.Any) -> str:
		if self._socket is None:
			self._lock.acquire()

		self._pending_selection = options
		while True:
			try:
				return self._select()
			except SelectionException:
				pass

	def set_socket(self, socket: JsonSocket):
		was_none = self._socket is None
		self._socket = socket

		for event, first in self.events:
			self._notify_event(event, first)

		if was_none:
			self._lock.release()

	def notify_event(self, event: Event, first: bool) -> None:
		self.events.append((event, first))
		if self._socket is not None:
			self._notify_event(event, first)


class SocketInterface(IOInterface):

	def __init__(self, ids: t.Iterable[str]) -> None:
		super().__init__()

		self._ids = tuple(ids) #type: t.Tuple[str, ...]
		self._connections = {
			_id: PlayerConnection()
			for _id in
			ids
		} #type: t.Dict[str, PlayerConnection]

		self._players = {} #type: t.Dict[GameObserver, PlayerConnection]

	def update_socket(self, player_id: str, socket: JsonSocket):
		self._connections[player_id].set_socket(socket)

	def bind_players(self, players: t.List[Player]) -> None:
		for _id, player in zip(self._ids, players):
			self._connections[_id].player = player
			self._players[player] = self._connections[_id]

	def select_option(
		self,
		player: GameObserver,
		options: io_options,
		optional: bool = False,
		additional_options: io_additional_options = None,
		reason: t.Optional[str] = None
	) -> io_option:
		return self.select_options(
			player = player,
			options = options,
			minimum = 0 if optional else 1,
			maximum = 1,
			additional_options = additional_options,
			reason = reason,
		)[0]

	def select_options(
		self,
	   player: GameObserver,
	   options: io_options,
	   minimum: t.Optional[int] = 1,
	   maximum: t.Optional[int] = None,
	   additional_options: io_additional_options = None,
	   reason: t.Optional[str] = None
   ) -> t.List[io_option]:

		_additional_options_in = additional_options if additional_options is not None else {}

		_options = list(options)

		_additional_options = {
			_stringify_option(option): option
			for option in _additional_options_in
		}


		_maximum = len(_options) if maximum is None else maximum
		_minimum = len(_options) if minimum is None else minimum

		end_picks = 'DONE'

		picked = []
		for _ in range(_maximum):
			message = {
				'type': 'select',
				'options': (
					[_jsonify(option, player) for option in _options]
					+ (
						[end_picks]
						if len(picked) > _minimum else
						[]
					)
				),
				'additional options': [
					_jsonify(key, player) for key in additional_options
				]
			}

			_looping = True
			while _looping:
				force_add_op = False

				choice = self._players[player].select(message)

				if choice and choice[0] == '-':
					choice = choice[1:]
					force_add_op = True

				pattern = re.compile(choice, re.IGNORECASE)

				if len(picked) > _minimum and choice and pattern.match(end_picks):
					return picked

				if not force_add_op:
					for i in range(len(_options)):
						if pattern.match(_stringify_option(_options[i])):
							picked.append(_options.pop(i))
							_looping = False
							break

				if not picked:
					for key in _additional_options:
						if pattern.match(key):
							return _additional_options[key]

		return picked

	def notify_event(self, event: Event, player: GameObserver, first: bool) -> None:
		self._players[player].notify_event(event, first)

# def notify_event(self, event: Event) -> None:
	# 	# print(
	# 	# 	'{}: {}'.format(
	# 	# 		event.__class__.__name__,
	# 	# 		event.values,
	# 	# 	)
	# 	#
	# 	# )
	# 	for connection in self._connections.values():
	# 		connection.notify_event(event)