import asyncio
import dataclasses
from typing import Any, Callable, LiteralString

import aiomysql as sql
import httpx
from nonebot import get_driver

headers = {
    'Authorization': get_driver().config.api_token
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
    DB_NAME = 'hikari_recent_db'
    INIT_SQL_NAME = './create.sql'
    CREATED = False
    SQL_LOOP = asyncio.get_event_loop()
    INIT_SQL = ''

    url: LiteralString = 'https://api.wows.shinoaki.com'
    queryUserInfo: LiteralString = 'public/wows/account/user/info'
    queryUserMap: LiteralString = '/public/wows/bind/account/platform/bind/list'
    resolver: Callable

    def __init__(self):
        self.entity: sql.connection.Connection = None
        self.cursor: sql.cursors.Cursor = None
        self.table_name: list[str] = None
        self.table: dict[str, list[str]] = None

    @classmethod
    async def factory():
        self = localDB()
        if not self.CREATED:
            secert = ''
            with open('./secert.txt')  as s:
                secert = s.read()
            self.entity: sql.connection.Connection = await sql.connect(host='localhost', user='root', password=secert, db=self.DB_NAME, loop=self.SQL_LOOP)
            self.cursor: sql.cursors.Cursor = await self.entity.cursor()
            with open(self.INIT_SQL_NAME) as file:
                self.INIT_SQL = file.read()
            await self.cursor.execute(self.INIT_SQL)

            await self.cursor.execute(f'select table_name from information_schema.tables where table_schema="{self.DB_NAME}" and table_type="base table"')
            self.table_name = [name[0] for name in await self.cursor.fetchall()]
            self.table = {}
            for name in self.table_name:
                await self.cursor.execute(f'select column_name from information_schema.columns where table_name="{name}"')
                self.table[name] = [name[1] for name in await self.cursor.fetchall()]

            self.CREATED = True

            await self.refreshColorCache()

    def __del__(self):
        self.cursor.close()
        self.entity.close()


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
    async def refreshColorCache(self) -> None:
        raw = await self.getFromTable('COLOR', all=True)
        self.colorCache = dict(raw)

    def colorExist(self, color: str) -> bool:
        return color in self.colorCache.values()

    def getColorId(self, color: str) -> int:
        return [key for key in self.colorCache.keys() if self.colorCache[key] == color][0]

    def getColor(self, id: int) -> str:
        return self.colorCache[id]

    async def setColor(self, color: str) -> None:
        await self.insertIntoTable('COLOR', color=color)
        await self.refreshColorCache()

    # Basic io from database
    async def exec(self, command: str, all: bool = False):
        await self.cursor.execute(command)
        await self.entity.commit()
        if all:
            return await self.cursor.fetchall()
        else:
            return await self.cursor.fetchone()

    async def getFromTable(self, table: str, *args, orderBy: str | None = None, all: bool = False, desc: bool = True, **kwargs) -> list:
        if table not in self.table_name:
            raise ValueError(f'Table {table} not found.')
        for name in args:
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')
        for name in kwargs.keys():
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')

        nameStr = self.expandList(*args)
        condition = self.expandDict(table, **kwargs)

        return await self.exec(f'''
            select {nameStr}
            from {table}
            {'' if condition == '' else 'where '}{condition}
            {f"order by {orderBy} {'desc' if desc else 'asc'}" if orderBy is not None else ''}
        ''', all)

    async def insertIntoTable(self, table: str, *args, **kwargs) -> None:
        if table not in self.table_name:
            raise ValueError(f'Table {table} not found.')
        for name in args:
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')
        for name in kwargs.keys():
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')

        if len(kwargs) != 0:
            await self.exec(f'''
                insert into {table} ({self.expandList(*kwargs.keys())})
                values ({self.expandList(*kwargs.values())})
            ''')
        elif len(args) != 0:
            await self.exec(f'''
                insert into {table}
                values ({self.expandList(*args)})
            ''')

    async def updateToTable(self, table: str, condition: dict, updateValue: dict) -> None:
        if table not in self.table_name:
            raise ValueError(f'Table {table} not found.')
        for name in condition.keys():
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')
        for name in updateValue.keys():
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')

        if len(updateValue) != 0:
            await self.exec(f'''
                update {table}
                set {self.expandDict('', **updateValue)}
                where {self.expandDict('', **condition)}
            ''')

    # Upper level io
    async def getLocalQueryId(self, **kwargs) -> list[int]:
        raw = self.getFromTable('QUERY', 'ID', **kwargs)
        return [id[0] for id in raw]

    async def getLocalQuery(self, id: int) -> query:
        raw = self.getFromTable('QUERY', ID=id)
        return query(*raw[1:])

    async def qqid2wgid(self, id: str | int, getDefault: bool = True) -> list[str]:
        if getDefault:
            return [x[0] for x in self.getFromTable('USERS', 'ID', all=True, localID=id, isDefault=True)]
        else:
            return [x[0] for x in self.getFromTable('USERS', 'ID', all=True, localID=id)]

    async def renewRecord(self, userID: int, renewEntity: dict[str, query], time: int, shipID: str = 'null') -> None:
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
                renewDict = renewEntity[renew].dict__
                self.insertIntoTable('QUERY', **renewDict)
                lastInfo[renew] = self.getLocalQueryId(**renewDict)[0]

            for key, value in zip(lastInfo.keys(), lastInfo.values()):
                if isinstance(value, query):
                    lastInfo[key] = self.getLocalQueryId(**value.dict__)[0]

            self.insertIntoTable('USER_INFO', **lastInfo, queryTime=time)
        self.entity.commit()

    # Top level io
    async def getInfo(self, qqId: str | int) -> dict:
        wgid = self.qqid2wgid(qqId)
        records = self.getFromTable('USER_INFO', orderBy='queryTime', userID=wgid, shipID='null')

    async def getShipInfo(self, qqId: str | int, shipId: str | int) -> dict:
        pass

    async def getRecent(self, qqId: str | int, timeBack: int) -> dict:
        pass

    async def getShipRecent(self, qqId: str | int, shipId: str | int, timeBack: int) -> dict:
        pass

    async def refreshQQUsers(self, userList: dict[int, str]) -> None:
        userListLocal = [id[0] for id in self.getFromTable('LOCAL_USERS', 'ID', all=True)]
        for user in userList.keys():
            if user not in userListLocal:
                self.insertIntoTable('LOCAL_USERS', ID=user, userName=userList[user])
                userListLocal.append(user)

        userMapLocal = dict(self.getFromTable('USERS', 'ID', 'localID', all=True))
        async with httpx.AsyncClient(headers=headers) as client:
            params = {
                'platformType': 'QQ',
                'platformId': ''
            }
            for user in userListLocal:
                params['platformId'] = str(user)
                maps = await client.get(self.url + self.queryUserMap, params=params, follow_redirects=True)
                maps = maps.json()['data']


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

localDB.resolver = resolveShinoakiAPI

# Running in another thread
class queryRequester:
    db: localDB
    timegap: int = 15
    shouldRunning: bool = True

    @staticmethod
    async def request():
        users = await queryRequester.db.getFromTable('USERS', 'ID', 'serverName', all=True)

        for user in users:
            getParam = {
                'accountID': user[0],
                'server': user[1]
            }
            async with httpx.AsyncClient(headers=headers) as client:
                raw = await client.get(url=queryRequester.db.url + queryRequester.db.queryUserInfo,
                                params=getParam,
                                follow_redirects=True)
                result = raw.json()
                if result['status'] != 'ok':
                    raise ConnectionError('Remote status not ok.')
                entity = queryRequester.db.resolver(result['data'], queryRequester.db)
                queryRequester.db.renewRecord(user[0], entity, result['queryTime'])
