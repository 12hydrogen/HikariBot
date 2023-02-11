import asyncio
import dataclasses
import enum
import time
from typing import Any, Callable, LiteralString

import aiomysql as sql
import httpx
from nonebot import get_driver

headers = {
    #'Authorization': get_driver().config.api_token
}

@dataclasses.dataclass()
class query:
    battleCount: int
    PR: int
    damage: int
    damageColor: int
    winRate: float
    winRateColor: int
    kdRate: float
    hitRate: float


class localDB(object):
    DB_NAME = 'hikari_recent_db'
    INIT_SQL_NAME = './create.sql'
    CREATED = False
    INIT_SQL = ''
    OUTDATE = 180 * 24 * 60 * 60 # 180 days

    url: LiteralString = 'https://api.wows.shinoaki.com'
    queryUserInfo: LiteralString = '/public/wows/account/user/info'
    queryUserMap: LiteralString = '/public/wows/bind/account/platform/bind/list'
    queryUserClan: LiteralString = '/public/wows/account/search/clan/user'

    def __init__(self):
        self.entity: sql.connection.Connection = None
        self.cursor: sql.cursors.Cursor = None

        self.table_name: list[str] = None
        self.table: dict[str, list[str]] = None
        self.loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        self.resolver = self.resolveShinoakiAPI
        self.constructer = self.constructShinoakiAPI

        self.tables: enum = None

    @staticmethod
    async def factory():
        self: localDB = None
        self = localDB()
        if not self.CREATED:
            self.CREATED = True

            secert = ''
            with open('./secert.txt')  as s:
                secert = s.read().removesuffix('\n')
            self.entity: sql.connection.Connection = await sql.connect(
                user='root',
                password=secert,
                db=self.DB_NAME,
                loop=self.loop,
                connect_timeout=60
            )
            self.cursor: sql.cursors.Cursor = await self.entity.cursor()
            with open(self.INIT_SQL_NAME) as file:
                self.INIT_SQL = file.read()
            await self.cursor.execute(self.INIT_SQL)

            await self.cursor.execute(f'select table_name from information_schema.tables where table_schema="{self.DB_NAME}";')
            self.table_name = [x[0] for x in await self.cursor.fetchall()]
            self.tables = enum.Enum('tables', dict(zip(self.table_name, self.table_name)))

            self.table = {}
            for name in self.table_name:
                await self.cursor.execute(f'select column_name from information_schema.columns where table_name="{name}";')
                self.table[name] = [x[0] for x in await self.cursor.fetchall()]
                self.tables[name].columns = enum.Enum(f'{name}_columns', dict(zip(self.table[name], self.table[name])))



            await self.refreshColorCache()
        return self

    async def destroy(self):
        await self.cursor.close()
        await self.entity.ensure_closed()

    @staticmethod
    def converter(value: Any) -> str:
        if isinstance(value, bool):
            return str(int(value))
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, float):
            return f'{value:.2}'
        else:
            return f'"{value}"'
    @staticmethod
    def expandList(*args, divider: str = ', ', isKey: bool = False) -> str:
        if len(args) != 0:
            if isKey:
                return divider.join([f'{x}' for x in args])
            else:
                return divider.join([f'{localDB.converter(x)}' for x in args])
        else:
            return '*'

    @staticmethod
    def expandDict(table: str, divider: str = '\n', **kwargs) -> str:
        if len(kwargs) != 0:
            pairs = []
            for name, value in zip(kwargs.keys(), kwargs.values()):
                if table != '':
                    name = f'{table}.{name}'
                if value is None:
                    value = ' is null'
                else:
                    value = f'={localDB.converter(value)}'
                pairs.append(f'{name}{value}')
            return divider.join(pairs)
        else:
            return ''

    # Color cache
    async def refreshColorCache(self) -> None:
        raw = await self.getFromTable('COLOR', all=True)
        self.colorCache = dict(raw)

    def colorExist(self, color: str) -> bool:
        return color in self.colorCache.values()

    async def getColorId(self, color: str) -> int:
        id = [key for key in self.colorCache.keys() if self.colorCache[key] == color]
        if len(id) == 0:
            await self.setColor(color)
            id = [key for key in self.colorCache.keys() if self.colorCache[key] == color]
        return id[0]

    def getColor(self, id: int) -> str:
        return self.colorCache[id]

    async def setColor(self, color: str) -> None:
        await self.insertIntoTable('COLOR', color=color)
        await self.refreshColorCache()

    # Basic io from database
    async def exec(self, command: str, all: bool = False) -> list:
        await self.cursor.execute(command)
        await self.entity.commit()
        if all:
            return await self.cursor.fetchall()
        else:
            return await self.cursor.fetchone()

    # Secondary io
    async def getFromTable(self, table: str, *args, orderBy: str | None = None, all: bool = False, desc: bool = True, **kwargs) -> list:
        nameStr = self.expandList(*[self.tables[table].columns[name].value for name in args], isKey=True)
        condition = self.expandDict(self.tables[table].value, ' and ', **kwargs)

        return await self.exec(f'''
            select {nameStr}
            from {table}
            {'' if condition == '' else 'where '}{condition}
            {f"order by {orderBy} {'desc' if desc else 'asc'}" if orderBy is not None else ''};
        ''', all)

    async def insertIntoTable(self, table: str, **kwargs) -> None:
        if len(kwargs) != 0:
            await self.exec(f'''
                insert into {table} ({self.expandList(*[self.tables[table].columns[name].value for name in kwargs.keys()], isKey=True)})
                values ({self.expandList(*kwargs.values())});
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
                where {self.expandDict('', **condition)};
            ''')

    async def existInTable(self, table: str, **kwargs) -> bool:
        if table not in self.table_name:
            raise ValueError(f'Table {table} not found.')
        for name in kwargs.keys():
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')

        if len(kwargs) != 0:
            await self.exec(f'''
                select * from {table}
                where {self.expandDict('', ' and ', **kwargs)};
            ''')
            if self.cursor.rowcount > 0:
                return True
            else:
                return False

    async def deleteFromTable(self, table: str, condition: str = None, **kwargs):
        if table not in self.table_name:
            raise ValueError(f'Table {table} not found.')
        for name in kwargs.keys():
            if name not in self.table[table]:
                raise ValueError(f'Name {name} not found.')

        if len(kwargs) != 0:
            await self.exec(f'''
                delete from {table}
                where {self.expandDict('', ' and ', **kwargs) if condition is None else condition};
            ''')

    # Upper level io
    async def getLocalQueryId(self, **kwargs) -> list[int]:
        raw = await self.getFromTable('QUERY', 'ID', **kwargs)
        return [id[0] for id in raw]

    async def getLocalQuery(self, id: int) -> query:
        raw = await self.getFromTable('QUERY', ID=id)
        return query(*raw[1:])

    async def qqid2wgid(self, id: str | int, getDefault: bool = True) -> list[str]:
        if getDefault:
            return [x[0] for x in await self.getFromTable('USERS', 'ID', all=True, localID=id, isDefault=True)]
        else:
            return [x[0] for x in await self.getFromTable('USERS', 'ID', all=True, localID=id)]

    async def renewRecord(self, userID: int, renewEntity: dict[str, query], time: int, shipID: str | None = None) -> None:
        lastInfoRaw = await self.getFromTable('USER_INFO', *queryToGet, orderBy='queryTime', userID=userID, shipID=shipID)
        queryToRenew = []
        lastInfo = {}
        if lastInfoRaw is not None:
            lastInfo = dict(zip(queryToGet, [await self.getLocalQuery(id) for id in lastInfoRaw]))
            for key, value in zip(renewEntity.keys(), renewEntity.values()):
                if value != lastInfo[key]:
                    queryToRenew.append(key)
        else:
            queryToRenew = queryToGet

        if len(queryToRenew) == 0:
            # Nothing to renew, only update the timestamp
            await self.updateToTable('USER_INFO', dict(zip(queryToGet, lastInfoRaw)), {'queryTime': time})
        else:
            # At least one record need update
            for renew in queryToRenew:
                renewDict = renewEntity[renew].__dict__
                await self.insertIntoTable('QUERY', **renewDict)
                lastInfo[renew] = (await self.getLocalQueryId(**renewDict))[0]

            for key, value in zip(lastInfo.keys(), lastInfo.values()):
                if isinstance(value, query):
                    lastInfo[key] = (await self.getLocalQueryId(**value.__dict__))[0]

            await self.insertIntoTable('USER_INFO', **lastInfo, queryTime=time)
        await self.entity.commit()

    async def cleanUpOutOfDate(self, time: int) -> None:
        outDateTime = time - self.OUTDATE
        await self.deleteFromTable('USER_INFO', condition=f'queryTime<{outDateTime}')
        allUsedQuery = []
        for info in await self.getFromTable('USER_INFO', *queryToGet, orderBy='queryTime', desc=False, all=True):
            allUsedQuery.extend(info)
        await self.deleteFromTable('QUERY', condition=f'ID not in ({self.expandList(*allUsedQuery)})')

    # Top level io
    async def getInfo(self, qqId: str, shipId: int = None) -> dict:
        wgid = self.qqid2wgid(qqId)
        queryRequester.query()
        records = await self.getFromTable('USER_INFO', *queryToGet, 'clanID', orderBy='queryTime', userID=wgid, shipID=shipId)
        records = dict(zip(queryToGet + ['clanID'], [await self.getLocalQuery(id) for id in records[0:-1]] + [records[-1]]))
        return await self.constructer(records)

    async def getRecent(self, qqId: str, shipId: int = None, timeBack: int = 1) -> dict:
        pass

    async def refreshQQUsers(self, userList: dict[str, str]) -> None:
        userListLocal = [x[0] for x in await self.getFromTable('LOCAL_USERS', 'ID', all=True)]
        for user in userList.keys():
            if user not in userListLocal:
                await self.insertIntoTable('LOCAL_USERS', ID=user, userName=userList[user])
                userListLocal.append(user)

        userMapLocal = dict(await self.getFromTable('USERS', 'ID', 'localID', all=True))
        existKeys = userMapLocal.keys()
        existValues = userMapLocal.values()
        async with httpx.AsyncClient(headers=headers, verify=False) as client:
            params = {
                'platformType': 'QQ',
                'platformId': ''
            }
            for user in userListLocal:
                params['platformId'] = str(user)
                maps = await client.get(self.url + self.queryUserMap, params=params, follow_redirects=True)
                maps = maps.json()
                if maps['ok']:
                    for bindUser in maps['data']:
                        if bindUser['accountId'] not in existKeys:
                            if not await self.existInTable('CLANS', ID=0):
                                await self.insertIntoTable('CLANS', ID=0)
                            await self.insertIntoTable('USERS',
                                ID=bindUser['accountId'],
                                localID=bindUser['platformId'],
                                userName=bindUser['userName'],
                                serverName=bindUser['serverType'],
                                clanID=0,
                                isDefault=bindUser['defaultId']
                            )
                            clanParams = {
                                'accountId': bindUser['accountId'],
                                'server': bindUser['serverType']
                            }
                            clanInfo = await client.get(self.url + self.queryUserClan, params=clanParams, follow_redirects=True)
                            clanInfo = clanInfo.json()
                            if clanInfo['ok']:
                                if not await self.existInTable('CLANS', ID=clanInfo['data']['clanId']):
                                    if not self.colorExist(clanInfo['data']['colorRgb']):
                                        await self.setColor(clanInfo['data']['colorRgb'])
                                    color = await self.getColorId(clanInfo['data']['colorRgb'])
                                    await self.insertIntoTable('CLANS', ID=clanInfo['data']['clanId'], tag=clanInfo['data']['tag'], color=color)
                                await self.updateToTable('USERS', {'ID': bindUser['accountId']}, {'clanID': clanInfo['data']['clanId']})

    # Resolver
    async def resolveShinoakiAPI(self, data: dict) -> dict[str, query]:
        resultDict = dict()

        async def resolveSingleQuery(data: dict) -> query:
            if not self.colorExist(data['damageData']['color']):
                await self.setColor(data['damageData']['color'])
            return query(
                data['battles'],
                data['pr']['value'],
                data['damage'],
                await self.getColorId(data['damageData']['color']),
                data['wins'],
                await self.getColorId(data['winsData']['color']),
                data['kd'],
                data['hit']
            )

        resultDict['totalQueryID'] = await resolveSingleQuery(data['pvp'])
        resultDict['soloQueryID'] = await resolveSingleQuery(data['pvpSolo'])
        resultDict['twoQueryID'] = await resolveSingleQuery(data['pvpTwo'])
        resultDict['threeQueryID'] = await resolveSingleQuery(data['pvpThree'])
        resultDict['rankQueryID'] = await resolveSingleQuery(data['rankSolo'])

        resultDict['bbQueryID'] = await resolveSingleQuery(data['type']['Battleship'])
        resultDict['crQueryID'] = await resolveSingleQuery(data['type']['Cruiser'])
        resultDict['ddQueryID'] = await resolveSingleQuery(data['type']['Destroyer'])
        resultDict['cvQueryID'] = await resolveSingleQuery(data['type']['AirCarrier'])
        resultDict['ssQueryID'] = await resolveSingleQuery(data['type']['Submarine'])

        return resultDict

    async def constructShinoakiAPI(self, data: dict[str, query]) -> dict:
        resultDict = dict()

        def consructSingleQuery(data: query) -> dict:
            return {
                'battles': data.battleCount,
                'pr': {
                    'value': data.PR
                },
                'damage': data.damage,
                'damageData': {
                    'color': self.getColor(data.damageColor)
                },
                'wins': data.winRate,
                'winsData': {
                    'color': self.getColor(data.winRateColor)
                },
                'kd': data.kdRate,
                'hit': data.hitRate
            }

        if data['clanID'] != 0:
            clanInfo =  await self.getFromTable('CLANS', 'tag', 'colorRgb', ID=data['clanID'])
            resultDict['clanInfo'] = {
                'tag': clanInfo[0],
                'colorRgb': self.getColor(clanInfo[1])
            }

        resultDict['pvp'] = consructSingleQuery(data['totalQuery'])
        resultDict['pvpSolo'] = consructSingleQuery(data['soloQuery'])
        resultDict['pvpTwo'] = consructSingleQuery(data['twoQuery'])
        resultDict['pvpThree'] = consructSingleQuery(data['threeQuery'])
        resultDict['rankSolo'] = consructSingleQuery(data['rankQuery'])

        resultDict['type'] = {
            'Battleship': consructSingleQuery(data['bbQuery']),
            'Cruiser': consructSingleQuery(data['crQuery']),
            'Destroyer': consructSingleQuery(data['ddQuery']),
            'AirCarrier': consructSingleQuery(data['cvQuery']),
            'Submarine': consructSingleQuery(data['ssQuery'])
        }

        return resultDict

queryToGet = ['totalQueryID', 'soloQueryID', 'twoQueryID', 'threeQueryID', 'rankQueryID', 'bbQueryID', 'crQueryID', 'ddQueryID', 'cvQueryID', 'ssQueryID']

# Running in another thread
class queryRequester:
    db: localDB
    loop: asyncio.AbstractEventLoop
    timegap: int = 5
    shouldRunning: bool = True
    lastRequestTime: float = 0.0

    @staticmethod
    async def query():
        users = await queryRequester.db.getFromTable('USERS', 'ID', 'serverName', all=True)
        for user in users:
            params = {
                'accountId': user[0],
                'server': user[1]
            }
            async with httpx.AsyncClient(headers=headers, verify=False) as client:
                raw = await client.get(url=queryRequester.db.url + queryRequester.db.queryUserInfo,
                                params=params,
                                follow_redirects=True)
                result = raw.json()
                if not result['ok']:
                    raise ConnectionError('Remote status not ok.')
                entity = await queryRequester.db.resolver(result['data'])
                curTime = int(time.time())
                await queryRequester.db.renewRecord(user[0], entity, curTime)
                await queryRequester.db.cleanUpOutOfDate(curTime)

    @staticmethod
    async def startQueryLoop():
        while queryRequester.shouldRunning:
            if time.time() - queryRequester.lastRequestTime > queryRequester.timegap * 60:
                await queryRequester.query()
                queryRequester.lastRequestTime = time.time()
            else:
                await asyncio.sleep(queryRequester.timegap * 60)


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    test = loop.run_until_complete(localDB.factory())
    queryRequester.db = test
    loop.run_until_complete(queryRequester.startQueryLoop())
    loop.run_until_complete(test.destroy())
