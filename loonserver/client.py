import typing as t
import threading
import socket as _socket

import random

from pysimplesoap.client import SoapClient

from loonserver.networking.jsonsocket import JsonSocket


class Receiver(threading.Thread):

	def __init__(self, socket: JsonSocket):
		super().__init__()
		self._socket = socket

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
				print(received['event_type'], received['values'])
			else:
				print(received)


TARGET = 'dominion.lost-world.dk'
# TARGET = 'localhost'
# target = 'http://dominion.lost-world.dk'

def create_game() -> str:
	client = SoapClient(
		location ='http://'+TARGET + ':8080',
		action ='http://'+TARGET + ':8080',
		namespace = "http://example.com/sample.wsdl",
		soap_ns = 'soap',
		ns="ns0",
	)

	response = client.create_game(game_id=random.randint(0, 4096))

	player_id = ''
	for item in response.ids:
		player_id = item

	return player_id

def test():

	player_id = create_game()
	# player_id = 'f4e954ec27176bd8b9ac9422e04dfe6bcfbe5c6260a802c59f1400b2c7435f0d'
	print('id: ', player_id)

	s = JsonSocket(_socket.AF_INET, _socket.SOCK_STREAM)
	print(TARGET)
	s.connect((TARGET, 9999))

	receiver = Receiver(s)
	receiver.start()

	s.send_json(
		{
			'type': 'connect',
			'id': str(player_id),
		}
	)

	receiver.join()

if __name__ == '__main__':
	test()