import dataclasses
import inspect
import sqlite3
import time
from typing import Callable, LiteralString

import httpx
from nonebot import get_driver

recentDB = sqlite3.connect('./recent.db')
defaultCursor = sqlite3.Cursor()

headers = {
    'Authorization': get_driver().config.api_token
}

@dataclasses
class query:
	battles: int
	pr: int
	damage: int
	damageColor: int
	winRate: float
	winRateColor: int
	kdRate: float
	hitRate: float

class localDB:
	__DB_NAME = './recent.db'
	__INIT_SQL_NAME = './create.sql'
	__CREATED = False

	def __init__(self):
		if not self.__CREATED:
			self.__entity = sqlite3.connect(self.__DB_NAME)
			self.__cursor = sqlite3.Cursor(self.__entity)
			self.__cursor.executescript(self.__INIT_SQL_NAME)

			self.__cursor.execute('select name from sqlite_master where type="table"')
			self.__table_name = [name[0] for name in self.__cursor.fetchall()]
			self.__table = {}
			for name in self.__table_name:
				self.__cursor.execute(f'pragma table_info({name})')
				self.__table[name] = [name[1] for name in self.__cursor.fetchall()]

			self.__CREATED = True

			self.refreshColorCache()

	@staticmethod
	def expandList(*args) -> str:
		if len(args) != 0:
			return ', '.join(args(map(str, args)))
		else:
			return '*'

	@staticmethod
	def expandDict(table: str, **kwargs) -> str:
		if len(kwargs) != 0:
			return '\n'.join([f'{"" if table == "" else f"{table}."}{name}={value}' for name, value in zip(dict.keys(), dict.values())])
		else:
			return ''

	# Validation
	def validTable(self, func: Callable, table: str, *args, **kwargs):
		def wrapper():
			rawArg = inspect.getargvalues(func)[0]
			if table not in self.__table_name:
				raise ValueError(f'Table {table} not found.')
			for name in args:
				if name not in self.__table[table]:
					raise ValueError(f'Name {name} not found.')
			for name in kwargs.keys():
				if name in rawArg:
					continue
				if name not in self.__table[table]:
					raise ValueError(f'Name {name} not found.')
			return func(table, *args, **kwargs)
		return wrapper

	# Color cache
	def refreshColorCache(self) -> None:
		raw = self.getFromTable('COLOR', all=True)
		self.__colorCache = dict([pair[0] for pair in raw], [pair[1] for pair in raw])

	def colorExist(self, color: str) -> bool:
		return color in self.__colorCache.values()

	def getColorId(self, color: str) -> int:
		return [key for key in self.__colorCache.keys() if self.__colorCache[key] == color][0]

	def getColor(self, id: int) -> str:
		return self.__colorCache[id]

	def setColor(self, color: str) -> int:
		self.insertIntoTable('COLOR', color=color)
		self.refreshColorCache()

	# Basic io from database
	@validTable
	def getFromTable(self, table: str, *args, orderBy: str | None = None, all: bool = False, desc: bool = False, **kwargs) -> list:
		nameStr = self.expandList(args)
		condition = self.expandDict(table, kwargs)

		self.__cursor.execute(f'''
			select {nameStr}
			from {table}
			{'' if condition == '' else 'where '}{condition}
			{f"order by {'desc' if desc else 'asc'}" if orderBy is not None else ''}
		''')
		if all:
			return list(self.__cursor.fetchall())
		else:
			return list(self.__cursor.fetchone())

	@validTable
	def insertIntoTable(self, table: str, *args, **kwargs) -> None:
		if len(kwargs) != 0:
			self.__cursor.execute(f'''
				insert into {table} ({self.expandList(kwargs.keys())})
				values ({self.expandList(kwargs.values())})
			''')
		elif len(args) != 0:
			self.__cursor.execute(f'''
				insert into {table}
				values ({self.expandList(args.values())})
			''')
		self.__entity.commit()

	@validTable
	def updateToTable(self, table: str, condition: dict, updateValue: dict) -> None:
		for name in condition.keys():
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')
		for name in updateValue.keys():
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')
		if len(updateValue) != 0:
			self.__cursor.execute(f'''
				update {table}
				set {self.expandDict('', updateValue)}
				where {self.expandDict('', condition)}
			''')
		self.__entity.commit()

	# Upper level io
	def getLocalQueryId(self, **kwargs) -> list[int]:
		raw = self.getFromTable('QUERY', 'ID', **kwargs)
		return [id[0] for id in raw]

	def getLocalQuery(self, id: int) -> query:
		raw = self.getFromTable('QUERY', ID=id)
		return query(raw[1:])

	def qqid2wgid(self, id: str | int) -> list[str]:
		return [x[0] for x in self.getFromTable('USERS', 'ID', all=True, localID=id)]

	def renewRecord(self, userID: int, renewEntity: dict[str, query], time: int) -> None:
		lastInfoRaw = self.getFromTable('USER_INFO', *queryToGet, orderBy='queryTime', desc=True, userID=userID)
		lastInfo = dict(queryToGet, [self.getLocalQuery(id) for id in lastInfoRaw])

		queryToRenew = []
		for key, value in zip(renewEntity.keys(), renewEntity.values()):
			if value != lastInfo[key]:
				queryToRenew.append(key)

		if len(queryToRenew) == 0:
			# Nothing to renew, only update the timestamp
			self.updateToTable('USER_INFO', dict(queryToGet, lastInfoRaw), {'queryTime': time})
		else:
			# At least one record need update
			for renew in queryToRenew:
				renewDict = dict([name for name in query.dir() if not (name.startswith('__') and name.endswith('__'))], renewEntity[renew])
				self.insertIntoTable('QUERY', **renewDict)
				lastInfo[renew] = self.getLocalQueryId(**renewDict)

			for key, value in zip(lastInfo.keys(), lastInfo.values()):
				if isinstance(value, query):
					lastInfo[key] = self.getLocalQueryId(**value.__dict__())

			self.insertIntoTable('USER_INFO', **lastInfo)
		self.__entity.commit()


queryToGet = ['totalQueryID', 'soloQueryID', 'twoQueryID', 'threeQueryID', 'rankQueryID', 'bbQueryID', 'crQueryID', 'ddQueryID', 'cvQueryID', 'ssQueryID']

def resolveShinoakiAPI(data: dict, db: localDB) -> dict[str, query]:
	resultDict = dict()

	def resolveSingleQuery(data: dict) -> query:
		if not db.colorExist(data['damageData']['color']):
			db.setColor(data['damageData']['color'])
		return query(
			data['battles'],
			data['pr']['value'],
			data['wins'],
			data['damage'],
			db.getColorId(data['damageData']['color']),
			data['wins'],
			db.getColorId(data['winsData']['color']),
			data['kd'],
			data['hit']
		)

	resultDict['totalQueryID'] = resolveSingleQuery(data['pvp'])
	resultDict['soloQueryID'] = resolveSingleQuery(data['pvpSolo'])
	resultDict['twoQueryID'] = resolveSingleQuery(data['pvpTwo'])
	resultDict['threeQueryID'] = resolveSingleQuery(data['pvpThree'])
	resultDict['rankQueryID'] = resolveSingleQuery(data['rankSolo'])

	resultDict['bbQueryID'] = resolveSingleQuery(data['type']['Battleship'])
	resultDict['crQueryID'] = resolveSingleQuery(data['type']['Cruiser'])
	resultDict['ddQueryID'] = resolveSingleQuery(data['type']['Destroyer'])
	resultDict['cvQueryID'] = resolveSingleQuery(data['type']['AirCarrier'])
	resultDict['ssQueryID'] = resolveSingleQuery(data['type']['Submarine'])

	return resultDict

# Running in another thread
def queryTimer(db: localDB, timegap: int = 15,
	url: LiteralString = 'https://api.wows.shinoaki.com',
	queryUserInfo: LiteralString = 'public/wows/account/user/info',
	resolver: Callable[[dict, localDB], dict[str, query]] = resolveShinoakiAPI
):
	while(True):
		users = db.getFromTable('USERS', 'ID', 'serverName', all=True)

		for user in users:
			getParam = {
				'accountID': user[0],
				'server': user[1]
			}
			with httpx.Client(headers=headers) as client:
				raw = client.get(url=url + queryUserInfo, params=getParam)
				result = raw.json()
				entity = resolver(result['data'], db)
				db.renewRecord(user[0], entity, result['queryTime'])

		time.sleep(60 * timegap)
