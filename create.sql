-- Enum table
create table if not exists COLOR(
	colorID int not null auto_increment,
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
	tag VARCHAR(16),
	color int,

	primary key(ID),
	foreign key(color) references COLOR (colorID)
);
-- Table for QQ info
create table if not exists LOCAL_USERS(
	ID VARCHAR(32) not null,
	userName VARCHAR(64) not null,

	primary key(ID)
);
-- Table for WG info
create table if not exists USERS(
	ID int not null,
	localID VARCHAR(32) not null,
	userName VARCHAR(64) not null,
	serverName VARCHAR(16) not null,
	clanID int not null,
	isDefault boolean not null,

	primary key(ID),
	foreign key(clanID) references CLANS (ID),
	foreign key(localID) references LOCAL_USERS (ID)
);
create table if not exists SHIPS(
	ID int not null,
	userID int not null,
	shipID int not null,

	primary key(ID),
	foreign key(userID) references USERS (ID),
	foreign key(shipID) references SHIP (shipID)
);
-- Insert each query, used by user query, ship query and recent query
create table if not exists QUERY(
	-- Stable info
	ID int not null auto_increment,
	-- battleCount info
	battleCount int not null,
	-- PR info
	PR int not null,
	-- damage info
	damage int not null,
	damageColor int not null,
	-- winRate info
	winRate decimal(10, 4) not null,
	winRateColor int not null,
	-- kd
	kdRate decimal(10, 4) not null,
	-- hit
	hitRate decimal(10, 4) not null,

	primary key(ID),
	foreign key(damageColor) references COLOR (colorID),
	foreign key(winRateColor) references COLOR (colorID)
);
create table if not exists USER_INFO(
	queryID int not null,
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
	foreign key(userID) references USERS (ID),
	foreign key(totalQueryID) references QUERY (ID),
	foreign key(soloQueryID) references QUERY (ID),
	foreign key(twoQueryID) references QUERY (ID),
	foreign key(threeQueryID) references QUERY (ID),
	foreign key(rankQueryID) references QUERY (ID),
	foreign key(bbQueryID) references QUERY (ID),
	foreign key(crQueryID) references QUERY (ID),
	foreign key(ddQueryID) references QUERY (ID),
	foreign key(cvQueryID) references QUERY (ID),
	foreign key(ssQueryID) references QUERY (ID)
);

DROP PROCEDURE IF EXISTS add_index;
CREATE PROCEDURE add_index()
BEGIN
DECLARE  target_database VARCHAR(100);
DECLARE  target_table_name VARCHAR(100);
DECLARE  target_column_name VARCHAR(100);
DECLARE  target_index_name VARCHAR(100);
set target_table_name = 'USER_INFO';
set target_index_name = 'user_index';
SELECT DATABASE() INTO target_database;
IF NOT EXISTS (SELECT * FROM information_schema.statistics WHERE table_schema = target_database AND table_name = target_table_name AND index_name = target_index_name) THEN
    set @statement = "alter table `USER_INFO` add UNIQUE KEY user_index (userID, shipID)";
    PREPARE STMT FROM @statement;
    EXECUTE STMT;
END IF;
END;
CALL add_index();

DROP PROCEDURE IF EXISTS add_index;
CREATE PROCEDURE add_index()
BEGIN
DECLARE  target_database VARCHAR(100);
DECLARE  target_table_name VARCHAR(100);
DECLARE  target_column_name VARCHAR(100);
DECLARE  target_index_name VARCHAR(100);
set target_table_name = 'QUERY';
set target_index_name = 'query_index';
SELECT DATABASE() INTO target_database;
IF NOT EXISTS (SELECT * FROM information_schema.statistics WHERE table_schema = target_database AND table_name = target_table_name AND index_name = target_index_name) THEN
    set @statement = "alter table `QUERY` add UNIQUE KEY query_index (ID)";
    PREPARE STMT FROM @statement;
    EXECUTE STMT;
END IF;
END;
CALL add_index();
