import typing as t

import json

from socket import socket, AF_INET, SOCK_STREAM


class JsonSocket(socket):

	def __init__(self, family=AF_INET, type=SOCK_STREAM, proto=0, fileno=None, wrapping: socket = None):
		if wrapping is None:
			super().__init__(family, type, proto, fileno)
		else:
			self.recv = wrapping.recv
			self.send = wrapping.send

	def get_json(self) -> t.Optional[object]:
		b = b''
		while True:
			received = self.recv(1)

			if received==b'\n':
				try:
					return json.loads(b.decode('utf-8'))
				except json.JSONDecodeError:
					b = b''
			elif received == b'':
				return None

			b += received

	def send_json(self, obj: object) -> None:
		self.send(json.dumps(obj).encode('utf-8')+b'\n')