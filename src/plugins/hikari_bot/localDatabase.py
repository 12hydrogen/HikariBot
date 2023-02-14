import asyncio
import dataclasses
import time
from typing import Any

import aiomysql as sql
import httpx
from nonebot import get_driver

headers = {
    # 'Authorization': get_driver().config.api_token # YUJI API key
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

# Convert Python type into SQL type
def convertor(value, withQuote: bool = True) -> str:
    if isinstance(value, bool):
        return str(int(value))
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, column):
        return str(value)
    elif isinstance(value, condition):
        return str(value)
    elif isinstance(value, float):
        return f'{value:.2f}'
    elif withQuote:
        return f'"{value}"'
    else:
        return str(value)
class condition(object):

    def __init__(self, partA: Any, partB: Any, connector: str):
        self.A = partA
        self.B = partB
        self.mid = connector
        if (partB is None):
            self.__final = convertor(partA, False) + ' is null'
        else:
            self.__final = convertor(partA, False) + connector + convertor(partB)

    # Use some magic to convert operator into actual string
    # Turn & to 'and'
    def __and__(self, another):
        if isinstance(another, condition):
            return condition(self, another, ' and ')
        return condition(self, None, '')
    # Turn | to 'or'
    def __or__(self, another):
        if isinstance(another, condition):
            return condition(self, another, ' or ')
        return condition(self, None, '')
    # Turn += to 'and'
    # def __iand__(self, another) -> None:
    #     if isinstance(another, condition):
            # self = condition(self, another, ' and ')

    def __str__(self):
        return self.__final
    __repr__ = __str__

class column(object):

    def __init__(self, name: str):
        self.__name = name

    # Use some magic to convert operator into actual string
    def __lt__(self, value):
        return condition(self, value, '<')
    def __gt__(self, value):
        return condition(self, value, '>')
    def __le__(self, value):
        return condition(self, value, '<=')
    def __ge__(self, value):
        return condition(self, value, '>=')
    def __eq__(self, value):
        return condition(self, value, '=')
    def __ne__(self, value):
        return condition(self, value, '!=')

    def __lshift__(self, list):
        return condition(self, f'({", ".join(map(str, list))})', ' in ')
    def __rshift__(self, list):
        return condition(self, f'({", ".join(map(str, list))})', ' not in ')

    def __str__(self):
        return self.__name
    __repr__ = __str__

class table(object):

    def __init__(self, name: str, columns: list[str], database):
        self.name = name
        self.columns = columns
        self.columns_entity = dict(zip(self.columns, [column(x) for x in self.columns]))
        self.database = database

    # Request for column
    def __getattr__(self, __name: str) -> column:
        if __name in self.columns:
            return self.columns_entity[__name]
        raise IndexError('Column not exist.')

    # Basic convert, turning list to comma-seperated string
    @staticmethod
    def construct(values: list[column]) -> str:
        return ', '.join(map(convertor, values))

    # Four common usage to turn combined-data into string
    @staticmethod
    def make_conditions(arg: list[Any]) -> str:
        conditions = [x for x in arg if isinstance(x, condition)]
        additional_cond = [x for x in arg if isinstance(x, dict)]
        finalCondition: condition | None = None
        if len(conditions) != 0:
            finalCondition = conditions[0]
            for single in conditions[1:]:
                finalCondition = finalCondition & single
        elif len(additional_cond) != 0:
            finalCondition = condition(list(additional_cond[0].keys())[0], list(additional_cond[0].values())[0], '=')
            for singleCondition in additional_cond:
                for key in singleCondition.keys():
                    if key == finalCondition.A:
                        continue
                    finalCondition = finalCondition & condition(key, singleCondition[key], '=')
        if finalCondition != None:
            return str(finalCondition)
        else:
            return ''

    def make_columns(self, arg: list[Any]) -> str:
        cols = []
        for name in arg:
            if str(name) in self.columns:
                cols.append(str(name))
        return ', '.join(cols)

    def make_pairs(self, kwarg: dict[str, Any]) -> tuple[str, str]:
        pairs = dict()
        for columnName in kwarg.keys():
            if columnName in self.columns:
                pairs[columnName] = (columnName, kwarg[columnName])
        finalPairs = list(zip(*pairs.values()))
        return (', '.join(finalPairs[0]), ', '.join(map(convertor, finalPairs[1])))

    def make_assigns(self, kwarg: dict[str, Any]) -> str:
        pairs = []
        for columnName in kwarg.keys():
            if columnName in self.columns:
                pairs.append(f'{columnName}={convertor(kwarg[columnName])}')
        return ', '.join(pairs)

    async def __run(self, command: str, all: bool = False):
        return await self.database.execute(command, all)

    # Basic SQL command convertor
    async def select(self, *arg, orderby: column | None = None, all: bool = False, isAsc: bool = False) -> list:
        col = self.make_columns(arg)
        cod = self.make_conditions(arg)
        order = self.make_columns([orderby])
        asc = ''
        if isAsc:
            asc = ' asc '
        else:
            asc = ' desc '
        command = f'select {"*" if len(col) == 0 else f"{col}"} from {self.name}{"" if cod == "" else f" where {cod}"}{"" if orderby is None else f" order by {order}{asc}"};'
        return await self.__run(command, all)

    async def insert(self, **kwarg) -> None:
        pairs = self.make_pairs(kwarg)
        command = f'insert into {self.name} ({pairs[0]}) values ({pairs[1]});'
        await self.__run(command)

    async def update(self, *arg, **kwarg) -> None:
        cod = self.make_conditions(arg)
        assigns = self.make_assigns(kwarg)
        command = f'update {self.name} set {assigns}{"" if cod == "" else f" where {cod}"};'
        await self.__run(command)

    async def delete(self, *arg) -> None:
        cod = self.make_conditions(arg)
        command = f'delete from {self.name}{"" if cod == "" else f" where {cod}"};'
        await self.__run(command)

    async def exists(self, *arg) -> bool:
        cod = self.make_conditions(arg)
        command = f'select * from {self.name} where {cod};'
        await self.__run(command)
        if len(await self.__fetch(True)) == 0:
            return False
        else:
            return True


# Cache for some small table which act like convertor
class cache(table):

    def __init__(self, target: table, idName: str, contentName: str):
        super().__init__(target.name, target.columns, target.database)
        self.__cache = []
        self.__AName = idName
        self.__BName = contentName

    async def renew(self):
        self.__cache = await super().select(self.__AName, self.__BName, all=True)

    def getContent(self, id):
        for pair in self.__cache:
            if pair[0] == id:
                return pair[1]
        raise IndexError('ID not found.')

    async def getId(self, content):
        for pair in self.__cache:
            if pair[1] == content:
                return pair[0]
        await self.insert(**{self.__BName: content})
        await self.renew()
        for pair in self.__cache:
            if pair[1] == content:
                return pair[0]
        raise RuntimeError('Unknown error in inserting or renewing.')

    def __getitem__(self, id):
        return self.getContent(id)

    async def __call__(self, content):
        return await self.getId(content)

class localDB(object):
    DB_NAME = 'hikari_recent_db'
    INIT_SQL_NAME = './create.sql'
    CREATED = False
    INIT_SQL = ''
    OUTDATE = 180 * 24 * 60 * 60 # 180 days

    # YUJI API
    url: str = 'https://api.wows.shinoaki.com'
    queryUserInfo: str = '/public/wows/account/user/info'
    queryUserMap: str = '/public/wows/bind/account/platform/bind/list'
    queryUserClan: str = '/public/wows/account/search/clan/user'

    # WG API
    # url: LiteralString = 'https://api.wows.shinoaki.com'
    # queryUserInfo: LiteralString = '/public/wows/account/user/info'
    # queryUserMap: LiteralString = '/public/wows/bind/account/platform/bind/list'
    # queryUserClan: LiteralString = '/public/wows/account/search/clan/user'

    def __init__(self):
        self.entity: sql.Pool | None = None

        self.table_name: list[str] | None = None
        self.table: dict[str, list[str]] | None = None
        self.loop: asyncio.AbstractEventLoop = asyncio.get_running_loop()

        self.resolver = self.resolveShinoakiAPI
        self.constructer = self.constructShinoakiAPI

        self.tables: dict | None = None
        self.caches: dict | None = None

    @staticmethod
    async def factory():
        self: localDB | None = None
        self = localDB()
        if not self.CREATED:
            self.CREATED = True

            secert = ''
            with open('./secert.txt')  as s:
                secert = s.read().removesuffix('\n')
            self.entity: sql.Pool = await sql.create_pool(
                user='root',
                password=secert,
                db=self.DB_NAME,
                loop=self.loop,
                connect_timeout=60,
                maxsize=16,
                pool_recycle=8
            )
            con: sql.Connection
            cur: sql.Cursor
            async with self.entity.acquire() as con:
                async with con.cursor() as cur:
                    with open(self.INIT_SQL_NAME) as file:
                        self.INIT_SQL = file.read()
                    await cur.execute(self.INIT_SQL)

                    # Get all table name
                    await cur.execute(f'select table_name from information_schema.tables where table_schema="{self.DB_NAME}";')
                    self.table_name = [x[0] for x in await cur.fetchall()]
                    # Get all column name for each table
                    self.table = dict()
                    for name in self.table_name:
                        await cur.execute(f'select column_name from information_schema.columns where table_name="{name}";')
                        self.table[name] = [x[0] for x in await cur.fetchall()]

            # Gen table object
            self.tables = dict()
            for singleTable in self.table_name:
                self.tables[singleTable] = table(singleTable, self.table[singleTable], self)

            # Gen cache object
            self.caches = {
                'color': cache(self.tables['color'], 'colorID', 'color')
            }

            # We don't need to verify it here, so delete it
            del self.table

            # Renew cache
            for c in self.caches.values():
                await c.renew()

        # Return the object created
        return self

    async def destroy(self) -> None:
        await self.cursor.close()
        await self.entity.ensure_closed()

    def __getattr__(self, name: str) -> table | cache:
        if name in self.caches.keys():
            return self.caches[name]
        return self.tables[name]


    async def execute(self, command: str, all: bool):
        con: sql.Connection
        cur: sql.Cursor
        async with self.entity.acquire() as con:
            async with con.cursor() as cur:
                await cur.execute(command)
                await con.commit()
                if all:
                    return await cur.fetchall()
                else:
                    return await cur.fetchone()

    # Upper level io
    async def getLocalQueryId(self, **kwargs) -> int:
        raw = await self.query.select(self.query.ID, kwargs)
        return raw[0]

    async def getLocalQuery(self, id: int) -> query:
        raw = await self.query.select(self.query.ID==id)
        return query(*raw[1:])

    async def qqid2wgid(self, id: str | int, getDefault: bool = True) -> list[str]:
        if getDefault:
            return [x[0] for x in await self.users.select(
                self.users.ID,
                self.users.localID==id,
                self.users.isDefault==True,
                all=True
            )]
        else:
            return [x[0] for x in await self.users.select(
                self.users.ID,
                self.users.localID==id,
                all=True
            )]

    async def renewRecord(self, userID: int, renewEntity: dict[str, query], time: int, shipID: str | None = None) -> None:
        lastInfoRaw = await self.user_info.select(
            *queryToGet,
            self.user_info.userID==userID,
            self.user_info.shipID==shipID,
            orderby=self.user_info.queryTime
        )
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
            await self.user_info.update(self.user_info.queryTime==time, **dict(zip(queryToGet, lastInfoRaw)))
        else:
            # At least one record need update
            for renew in queryToRenew:
                renewDict = renewEntity[renew].__dict__
                await self.query.insert(**renewDict)
                lastInfo[renew] = await self.getLocalQueryId(**renewDict)

            for key, value in zip(lastInfo.keys(), lastInfo.values()):
                if isinstance(value, query):
                    lastInfo[key] = await self.getLocalQueryId(**value.__dict__)

            await self.user_info.insert(queryTime=time, userID=userID, **lastInfo)

    async def cleanUpOutOfDate(self, time: int) -> None:
        outDateTime = time - self.OUTDATE
        await self.user_info.delete(self.user_info.queryTime<outDateTime)
        allUsedQuery = []
        for info in await self.user_info.select(*queryToGet, orderby=self.user_info.queryTime, all=True):
            allUsedQuery.extend(info)
        await self.query.delete(self.query.ID>>allUsedQuery)

    # Top level io
    async def getInfo(self, qqId: str, shipId: int = None) -> dict:
        wgid = (await self.qqid2wgid(qqId))[0]
        await queryRequester.query()
        records = await self.user_info.select(
            *queryToGet,
            self.user_info.clanID,
            self.user_info.userID==wgid,
            self.user_info.shipID==shipId,
            orderby=self.user_info.queryTime
        )
        records = dict(zip(queryToGet + ['clanID'], [await self.getLocalQuery(id) for id in records[:-1]] + [records[-1]]))
        return await self.constructer(records)

    async def getRecent(self, qqId: str, shipId: int = None, timeBack: int = 1) -> dict:
        wgid = (await self.qqid2wgid(qqId))[0]
        await queryRequester.query()
        records = await self.user_info.select(
            *queryToGet,
            self.user_info.clanID,
            self.user_info.userID==wgid,
            self.user_info.shipID==shipId,
            orderby=self.user_info.queryTime
        )

    async def refreshQQUsers(self, userList: dict[str, str]) -> None:
        userListLocal = [x[0] for x in await self.local_users.select(self.local_users.ID, all=True)]
        for user in userList.keys():
            if user not in userListLocal:
                await self.local_users.insert(ID=user, userName=userList[user])
                userListLocal.append(user)

        userMapLocal = dict(await self.users.select('ID', 'localID', all=True))
        existKeys = userMapLocal.keys()
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
                            if not await self.clans.exists(self.clans.ID==0):
                                await self.clans.insert(ID=0)
                            await self.users.insert(
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
                                if not await self.clans.exists(self.clans.ID==clanInfo['data']['clanId']):
                                    color = await self.color.getId(clanInfo['data']['colorRgb'])
                                    await self.clans.insert(ID=clanInfo['data']['clanId'], tag=clanInfo['data']['tag'], color=color)
                                await self.users.update(self.users.ID==bindUser['accountId'], clanID=clanInfo['data']['clanId'])

    # Resolver
    async def resolveShinoakiAPI(self, data: dict) -> dict[str, query]:
        resultDict = dict()

        async def resolveSingleQuery(data: dict) -> query:
            return query(
                data['battles'],
                data['pr']['value'],
                data['damage'],
                await self.color.getId(data['damageData']['color']),
                data['wins'],
                await self.color.getId(data['winsData']['color']),
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
                    'color': self.color.getContent(data.damageColor)
                },
                'wins': data.winRate,
                'winsData': {
                    'color': self.color.getContent(data.winRateColor)
                },
                'kd': data.kdRate,
                'hit': data.hitRate
            }

        if data['clanID'] != 0:
            clanInfo =  await self.clans.select(self.clans.tag, self.clans.colorRgb, self.clans.ID==data['clanID'])
            resultDict['clanInfo'] = {
                'tag': clanInfo[0],
                'colorRgb': self.color.getContent(clanInfo[1])
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
        users = await queryRequester.db.users.select(
            queryRequester.db.users.ID,
            queryRequester.db.users.serverName,
            all=True)
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
