import typing as t

import json
import socket as _socket
import re
import threading

from eventtree.replaceevent import Event, Condition

from throneloon.game.artifacts.players import Player
from throneloon.game.artifacts.artifact import GameArtifact
from throneloon.game.artifacts.observation import GameObserver
from throneloon.io.interface import IOInterface, io_additional_options, io_option, io_options

from loonserver.networking.jsonsocket import JsonSocket


def _stringify_option(option: io_option):
	if isinstance(option, GameArtifact):
		return option.name
	elif isinstance(option, Condition):
		return option.source.name
	else:
		return option


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
		self.events = [] #type: t.List[Event]
		self._pending_selection = None #type: str

		self._lock = BinaryLock()
		self._lock.acquire()

		self._returned_json = None

	def _ask_player(self, options: str):
		self._socket.send_json(
			{
				'type': 'select',
				'options': options,
			}
		)
		self._returned_json = self._socket.get_json()
		self._lock.release()

	def _notify_event(self, event: Event):
		self._socket.send_json(
			{
				'type': 'event',
				'event_type': event.__class__.__name__,
				'values': str(event.values),
			}
		)

	def _select(self) -> str:
		self._ask_player(self._pending_selection)

		self._lock.acquire()

		self._pending_selection = None

		_res = self._returned_json

		if (
			not isinstance(_res, dict)
			or not _res.get('type', None) == 'option_response'
			or not isinstance(_res.get('selected', None), str)
		):
			raise SelectionException()

		return self._returned_json['selected']

	def select(self, options: str) -> str:
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

		for event in self.events:
			self._notify_event(event)

		if was_none:
			self._lock.release()

	def notify_event(self, event: Event) -> None:
		self.events.append(event)
		if self._socket:
			self._notify_event(event)


class SocketInterface(IOInterface):

	def __init__(self, ids: t.List[str]) -> None:
		super().__init__()
		self._ids = ids
		self._connections = {
			_id: PlayerConnection()
			for _id in
			ids
		} #type: t.Dict[str, PlayerConnection]
		self._players = {} #type: t.Dict[Player, PlayerConnection]

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
		pass

	def select_options(
		self,
	   player: Player,
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

		end_picks = 'finished selecting'

		picked = []
		for _ in range(_maximum):
			message = (
				str(player)
				+(
					': ({}) '.format(picked)
					if _maximum > 1 else
					''
				)
				+', options: '
				+ str(
					[_stringify_option(option) for option in _options]
					+ (
						[end_picks]
						if len(picked) > _minimum else
						[]
					)
				)
				+ (
					(
						' additional options: '
						+ str(
							[
								_stringify_option(key)
								+ (
									''
									if value is None else
									': ' + value
								)
								for key, value in _additional_options_in.items()
							]
						)
					) if not picked else ''
				)
				+ (
					', ' + reason
					if reason else
					''
				)
				+ ' | A: {}, B: {}, C: {}, h: {}, b: {}, l: {}, y: {}'.format(
					player.actions,
					player.buys,
					player.currency,
					len(player.hand),
					len(player.battlefield),
					len(player.library),
					len(player.graveyard),
				)
			)

			_looping = True
			last_valid = True
			choice = ''
			while _looping:
				force_add_op = False

				# choice = input(('' if last_valid else '"{}" invalid'.format(choice))+': ')
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

				last_valid = False

		return picked

	def notify_event(self, event: Event) -> None:
		# print(
		# 	'{}: {}'.format(
		# 		event.__class__.__name__,
		# 		event.values,
		# 	)
		#
		# )
		for connection in self._connections.values():
			connection.notify_event(event)