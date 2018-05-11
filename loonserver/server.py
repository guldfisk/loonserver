
import typing as t
import threading

from http.server import HTTPServer
from multiprocessing import Process
from socketserver import BaseRequestHandler, TCPServer

from pysimplesoap.server import SoapDispatcher, SOAPHandler

from loonserver.games.manager import GameManager, CreateGameException
from loonserver.networking.jsonsocket import JsonSocket
from throneloon.game.setup.setupinfo import SetupInfo


class SoapThread(threading.Thread):

	def __init__(self, game_manager: GameManager, address: str, port: int):
		super().__init__()
		self._address = address
		self._port = port
		self._dispatcher = None #type: SoapDispatcher
		self._game_manager = game_manager #type: GameManager

	def create_game(self, game_id: str, amount_players: int = 1) -> t.Optional[str]:
		try:
			ids = self._game_manager.create_game(game_id, SetupInfo(num_players=amount_players))
			print(ids)
			return ','.join(ids)
		except CreateGameException:
			pass

	def run(self):
		address_port = self._address + ':{}/'.format(self._port)

		self._dispatcher = SoapDispatcher(
			name = 'GameCreator',
			location = address_port,
			action = address_port,
			namespace ='lost-world.dk',
			prefix = 'ns0',
			documentation = 'hm',
			trace = True,
			debug = True,
			ns = True,
		)

		self._dispatcher.register_function(
			'create_game',
			self.create_game,
			returns = {'ids': str},
			args = {'game_id': str, 'amount_players': int},
		)

		print("Starting SOAP server...")
		with HTTPServer((self._address, self._port), SOAPHandler) as http_server:
			http_server.dispatcher = self._dispatcher
			http_server.serve_forever()


class GameConnectionServer(TCPServer):

	def __init__(self, game_manager: GameManager, server_address, RequestHandlerClass, bind_and_activate=True):
		super().__init__(server_address, RequestHandlerClass, bind_and_activate)
		self._game_manager = game_manager

	@property
	def game_manager(self) -> GameManager:
		return self._game_manager

	def shutdown_request(self, request):
		pass


class ConnectionHandler(BaseRequestHandler):

	server = None #type: GameConnectionServer
	request = None #type: JsonSocket

	def handle(self):
		request = JsonSocket(wrapping=self.request)

		response = request.get_json()

		if (
			not isinstance(response, dict)
			or not response.get('type', None) == 'connect'
			or not isinstance(response.get('id', None), str)
		):
			request.send_json({'type': 'connection', 'result': 'failed', 'reason': 'invalid connection'})
			return

		if not self.server.game_manager.player_id_registered(response['id']):
			request.send_json({'type': 'connection', 'result': 'failed', 'reason': 'invalid id'})
			return

		request.send_json({'type': 'connection', 'result': 'success'})
		self.server.game_manager.new_connection(self.request, response['id'])


class LoonServer(Process):

	def __init__(self, address: str):
		super().__init__()
		self._address = address
		self._soap_thread = None #type: SoapThread
		self._game_manager = None #type: GameManager

	def run(self):
		self._game_manager = GameManager(self._address)

		self._soap_thread = SoapThread(self._game_manager, self._address, 8080)
		self._soap_thread.start()

		with GameConnectionServer(
			self._game_manager,
			(self._address, 9999),
			ConnectionHandler
		) as server:
			print('starting socket server...')
			server.serve_forever()


def test():
	import sys
	domain = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
	server = LoonServer(domain)
	server.start()
	server.join()
	# soap_thread = SoapThread('localhost', 8080)
	# soap_thread.start()


if __name__ == '__main__':
	test()