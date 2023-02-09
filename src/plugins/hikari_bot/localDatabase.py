import dataclasses
import inspect
import sqlite3
import threading
import time
from typing import Any, Callable, LiteralString

import httpx
from nonebot import get_driver

headers = {
    'Authorization': '584003729:j2itJY5GEFy2tPlfh7RieBDCqKpAaBQVnNXOjkd5RBsah3'
}

@dataclasses.dataclass()
class query:
	battles: int
	pr: int
	damage: int
	damageColor: int
	winRate: float
	winRateColor: int
	kdRate: float
	hitRate: float

def constructShinoakiAPI(data: query) -> dict:
	pass

class localDB:
	__DB_NAME = './recent.db'
	__INIT_SQL_NAME = './create.sql'
	__CREATED = False

	def __init__(self):
		if not self.__CREATED:
			self.__entity = sqlite3.connect(self.__DB_NAME)
			self.__cursor = sqlite3.Cursor(self.__entity)
			self.__cursor.execute('pragma foreign_keys=ON')
			with open(self.__INIT_SQL_NAME) as file:
				self.__INIT_SQL = file.read()
			self.__cursor.executescript(self.__INIT_SQL)

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
			return ', '.join(list(map(str, args)))
		else:
			return '*'

	@staticmethod
	def expandDict(table: str, **kwargs) -> str:
		if len(kwargs) != 0:
			return '\n'.join([f'{"" if table == "" else f"{table}."}{name}={value}' for name, value in zip(kwargs.keys(), kwargs.values())])
		else:
			return ''

	# Color cache
	def refreshColorCache(self) -> None:
		raw = self.getFromTable('COLOR', all=True)
		self.__colorCache = dict(raw)

	def colorExist(self, color: str) -> bool:
		return color in self.__colorCache.values()

	def getColorId(self, color: str) -> int:
		return [key for key in self.__colorCache.keys() if self.__colorCache[key] == color][0]

	def getColor(self, id: int) -> str:
		return self.__colorCache[id]

	def setColor(self, color: str) -> None:
		self.insertIntoTable('COLOR', color=color)
		self.refreshColorCache()

	# Basic io from database
	def getFromTable(self, table: str, *args, orderBy: str | None = None, all: bool = False, desc: bool = True, **kwargs) -> list:
		if table not in self.__table_name:
			raise ValueError(f'Table {table} not found.')
		for name in args:
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')
		for name in kwargs.keys():
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')

		nameStr = self.expandList(*args)
		condition = self.expandDict(table, **kwargs)

		self.__cursor.execute(f'''
			select {nameStr}
			from {table}
			{'' if condition == '' else 'where '}{condition}
			{f"order by {orderBy} {'desc' if desc else 'asc'}" if orderBy is not None else ''}
		''')
		if all:
			return list(self.__cursor.fetchall())
		else:
			return list(self.__cursor.fetchone())

	def insertIntoTable(self, table: str, *args, **kwargs) -> None:
		if table not in self.__table_name:
			raise ValueError(f'Table {table} not found.')
		for name in args:
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')
		for name in kwargs.keys():
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')

		if len(kwargs) != 0:
			self.__cursor.execute(f'''
				insert into {table} ({self.expandList(*kwargs.keys())})
				values ({self.expandList(*kwargs.values())})
			''')
		elif len(args) != 0:
			self.__cursor.execute(f'''
				insert into {table}
				values ({self.expandList(*args)})
			''')
		self.__entity.commit()

	def updateToTable(self, table: str, condition: dict, updateValue: dict) -> None:
		if table not in self.__table_name:
			raise ValueError(f'Table {table} not found.')
		for name in condition.keys():
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')
		for name in updateValue.keys():
			if name not in self.__table[table]:
				raise ValueError(f'Name {name} not found.')

		if len(updateValue) != 0:
			self.__cursor.execute(f'''
				update {table}
				set {self.expandDict('', **updateValue)}
				where {self.expandDict('', **condition)}
			''')
		self.__entity.commit()

	# Upper level io
	def getLocalQueryId(self, **kwargs) -> list[int]:
		raw = self.getFromTable('QUERY', 'ID', **kwargs)
		return [id[0] for id in raw]

	def getLocalQuery(self, id: int) -> query:
		raw = self.getFromTable('QUERY', ID=id)
		return query(*raw[1:])

	def qqid2wgid(self, id: str | int, getDefault: bool = True) -> list[str]:
		if getDefault:
			return [x[0] for x in self.getFromTable('USERS', 'ID', all=True, localID=id, isDefault=True)]
		else:
			return [x[0] for x in self.getFromTable('USERS', 'ID', all=True, localID=id)]

	def renewRecord(self, userID: int, renewEntity: dict[str, query], time: int, shipID: str = 'null') -> None:
		lastInfoRaw = self.getFromTable('USER_INFO', *queryToGet, orderBy='queryTime', userID=userID, shipID=shipID)
		lastInfo = dict(zip(queryToGet, [self.getLocalQuery(id) for id in lastInfoRaw]))

		queryToRenew = []
		for key, value in zip(renewEntity.keys(), renewEntity.values()):
			if value != lastInfo[key]:
				queryToRenew.append(key)

		if len(queryToRenew) == 0:
			# Nothing to renew, only update the timestamp
			self.updateToTable('USER_INFO', dict(zip(queryToGet, lastInfoRaw)), {'queryTime': time})
		else:
			# At least one record need update
			for renew in queryToRenew:
				renewDict = renewEntity[renew].__dict__
				self.insertIntoTable('QUERY', **renewDict)
				lastInfo[renew] = self.getLocalQueryId(**renewDict)[0]

			for key, value in zip(lastInfo.keys(), lastInfo.values()):
				if isinstance(value, query):
					lastInfo[key] = self.getLocalQueryId(**value.__dict__)[0]

			self.insertIntoTable('USER_INFO', **lastInfo, queryTime=time)
		self.__entity.commit()

	# Top level io
	def getInfo(self, qqId: str | int):
		wgid = self.qqid2wgid(qqId)
		records = self.getFromTable('USER_INFO', orderBy='queryTime', userID=wgid, shipID='null')

	def getShipInfo(self, qqId: str | int, shipId: str | int):
		pass

	def getRecent(self, qqId: str | int, timeBack: int):
		pass

	def getShipRecent(self, qqId: str | int, shipId: str | int, timeBack: int):
		pass

queryToGet = ['totalQueryID', 'soloQueryID', 'twoQueryID', 'threeQueryID', 'rankQueryID', 'bbQueryID', 'crQueryID', 'ddQueryID', 'cvQueryID', 'ssQueryID']

def resolveShinoakiAPI(data: dict, db: localDB) -> dict[str, query]:
	resultDict = dict()

	def resolveSingleQuery(data: dict) -> query:
		if not db.colorExist(data['damageData']['color']):
			db.setColor(data['damageData']['color'])
		return query(
			data['battles'],
			data['pr']['value'],
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
class queryRequester:
	db: localDB
	timegap: int = 1
	url: LiteralString = 'https://api.wows.shinoaki.com'
	queryUserInfo: LiteralString = 'public/wows/account/user/info'
	resolver: Callable[[dict, localDB], dict[str, query]] = resolveShinoakiAPI

	@staticmethod
	def request():
		while(True):
			users = queryRequester.db.getFromTable('USERS', 'ID', 'serverName', all=True)

			for user in users:
				getParam = {
					'accountID': user[0],
					'server': user[1]
				}
				with httpx.Client(headers=headers) as client:
					raw = client.get(url=queryRequester.url + queryRequester.queryUserInfo, params=getParam)
					result = raw.json()
					entity = queryRequester.resolver(result['data'], db)
					queryRequester.db.renewRecord(user[0], entity, result['queryTime'])

			time.sleep(60 * queryRequester.timegap)

if __name__ == '__main__':
    testDB = localDB()
    queryRequester.db = testDB
