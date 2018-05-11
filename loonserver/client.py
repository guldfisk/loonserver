import typing as t
import threading
import socket as _socket
import sys

import random

from pysimplesoap.client import SoapClient

from loonserver.networking.jsonsocket import JsonSocket


class Receiver(threading.Thread):

	def __init__(self, socket: JsonSocket):
		super().__init__()
		self._socket = socket
		self._open_events = 1

	def run(self):
		while True:
			received = self._socket.get_json() #type: t.Dict
			if received is None:
				print('connection lost')
				break
			if received['type'] == 'select':
				print(received['options'])
				ind = input(': ')
				print('sending:', ind)
				self._socket.send_json(
					{
						'type': 'option_response',
						'selected': ind,
					}
				)
			elif received['type'] == 'event':
				if received['first']:
					self._open_events += 1
					print('-|'*self._open_events+received['event_type'], received['values'])
				else:
					print('-|'*self._open_events+received['event_type'], received['values'])
					self._open_events -= 1
			else:
				print(received)


# TARGET = 'dominion.lost-world.dk'
TARGET = domain = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
# target = 'http://dominion.lost-world.dk'

def create_game(game_id: int, amount_players: int = 1) -> str:
	client = SoapClient(
		location ='http://'+TARGET + ':8080',
		action ='http://'+TARGET + ':8080',
		namespace = "http://example.com/sample.wsdl",
		soap_ns = 'soap',
		ns="ns0",
	)

	response = client.create_game(game_id = game_id, amount_players = amount_players)

	player_id = ''
	for item in response.ids:
		player_id = item

	return player_id


def _create_game():
	game_id = random.randint(0, 4096)
	player_id = str(create_game(game_id=game_id, amount_players=2)).split(',')
	print(player_id)


def _join_game():
	_id = input('id: ')

	s = JsonSocket(_socket.AF_INET, _socket.SOCK_STREAM)

	socket_address = TARGET

	s.connect((socket_address, 9999))

	receiver = Receiver(s)
	receiver.start()

	s.send_json(
		{
			'type': 'connect',
			'id': str(_id),
		}
	)

	receiver.join()


commands = {
	'create game': _create_game,
	'join game': _join_game,
}


def test():
	while True:
		ind = input(': ')
		commands.get(ind, lambda : None)()


if __name__ == '__main__':
	test()