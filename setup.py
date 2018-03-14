from setuptools import setup

setup(
	name='loonserver',
	version='1.0',
	packages=['loonserver'],
	install_requires=[
		'frozendict',
		'ordered_dict',
	]
)