-- Enum table
create table if not exists COLOR(
	colorID integer not null autoincrement,
	color CHAR(8) unique,

	primary key(colorID)
);
create table if not exists SHIP(
	shipID int not null,
	shipNameEN VARCHAR(64) not null,
	shipNameCN VARCHAR(64) not null,

	primary key(shipID)
);
-- Stable table
create table if not exists CLANS(
	ID int not null,
	tag VARCHAR(16) not null,
	color int not null,

	primary key(ID),
	foreign key(color) references COLOR.colorID
);
-- Table for QQ info
create table if not exists LOCAL_USERS(
	ID int not null,
	userName VARCHAR(64) not null,

	primary key(ID)
);
-- Table for WG info
create table if not exists USERS(
	ID int not null,
	localID int not null,
	userName VARCHAR(64) not null,
	serverName VARCHAR(16) not null,
	clanID int not null,

	primary key(ID),
	foreign key(clanID) references CLANS.ID,
	foreign key(prColor) references COLOR.colorID,
	foreign key(localID) references LOCAL_USERS.ID
);
create table if not exists SHIPS(
	ID integer not null autoincrement,
	userID int not null,
	shipID int not null,

	primary key(ID),
	foreign key(userID) references USERS.ID,
	foreign key(shipID) references SHIP.shipID
);
-- Insert each query, used by user query, ship query and recent query
create table if not exists QUERY(
	-- Stable info
	ID integer not null autoincrement,
	-- battleCount info
	battleCount int not null,
	-- PR info
	PR int not null,
	-- damage info
	damage int not null,
	damageColor int not null,
	-- winRate info
	winRate float not null,
	winRateColor int not null,
	-- kd
	kdRate float not null,
	-- hit
	hitRate float not null,

	queryTime int not null,

	primary key(ID, queryType, queryTime),
	foreign key(battleCountColor, damageColor, winRateColor) references COLOR.colorID
);
create table if not exists USER_INFO(
	queryID integer not null autoincrement,
	queryTime int not null,
	userID int not null,
	-- NULL if it represents total info
	shipID int,

	-- Queries for total info (user or ship)
	totalQueryID int not null,
	soloQueryID int not null,
	twoQueryID int not null,
	threeQueryID int not null,
	rankQueryID int not null,

	-- Queries for each type of ship (NULL when shipID is not NULL)
	bbQueryID int,
	crQueryID int,
	ddQueryID int,
	cvQueryID int,
	ssQueryID int,

	primary key(queryID),
	foreign key(userID) references USERS.ID,
	foreign key(
		totalQueryID,
		soloQueryID,
		twoQueryID,
		threeQueryID,
		rankQueryID,
		bbQueryID,
		crQueryID,
		ddQueryID,
		cvQueryID,
		ssQueryID
	) references QUERY.ID
);

create index if not exists user_index
on USER_INFO (userID, shipID);

create index if not exists query_index
on QUERY (ID);
