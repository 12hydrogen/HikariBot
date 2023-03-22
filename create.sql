-- create database if not exists hikari_recent_db;
-- Enum table
create table if not exists color(
	colorID integer not null autoincrement,
	color CHAR(8) unique,

	primary key(colorID)
);
create table if not exists ship(
	shipID integer not null,
	shipType VARCHAR(16) not null,
	shipNameEN VARCHAR(64) not null,
	shipNameCN VARCHAR(64) not null,

	primary key(shipID)
);
-- Stable table
create table if not exists clans(
	ID integer not null,
	tag VARCHAR(16),
	color integer,

	primary key(ID),
	foreign key(color) references color (colorID)
);
-- Table for QQ info
create table if not exists local_users(
	ID VARCHAR(32) not null,
	userName VARCHAR(64) not null,

	primary key(ID)
);
-- Table for WG info
create table if not exists users(
	ID integer not null,
	localID VARCHAR(32) not null,
	userName VARCHAR(64) not null,
	serverName VARCHAR(16) not null,
	clanID integer not null,
	isDefault boolean not null,

	primary key(ID),
	foreign key(clanID) references clans (ID),
	foreign key(localID) references local_users (ID)
);
-- Insert each query, used by user query, ship query and recent query
create table if not exists query(
	-- Stable info
	ID integer not null autoincrement,
	-- battleCount info
	battleCount integer not null,
	-- PR info
	PR integer not null,
	-- damage info
	damage integer not null,
	damageColor integer not null,
	-- winRate info
	winRate decimal(10, 4) not null,
	winRateColor integer not null,
	-- kd
	kdRate decimal(10, 4) not null,
	-- hit
	hitRate decimal(10, 4) not null,

	primary key(ID),
	foreign key(damageColor) references color (colorID),
	foreign key(winRateColor) references color (colorID)
);
create table if not exists user_info(
	queryID integer not null autoincrement,
	queryTime integer not null,
	userID integer not null,
	-- NULL if it represents total info
	shipID integer,

	-- Misc info
	shipRank integer,

	-- Queries for total info (user or ship)
	totalQueryID integer not null,
	soloQueryID integer not null,
	twoQueryID integer not null,
	threeQueryID integer not null,
	rankQueryID integer not null,

	-- Queries for each type of ship (NULL when shipID is not NULL)
	bbQueryID integer,
	crQueryID integer,
	ddQueryID integer,
	cvQueryID integer,
	ssQueryID integer,

	primary key(queryID),
	foreign key(userID) references users (ID),
	foreign key(totalQueryID) references query (ID),
	foreign key(soloQueryID) references query (ID),
	foreign key(twoQueryID) references query (ID),
	foreign key(threeQueryID) references query (ID),
	foreign key(rankQueryID) references query (ID),
	foreign key(bbQueryID) references query (ID),
	foreign key(crQueryID) references query (ID),
	foreign key(ddQueryID) references query (ID),
	foreign key(cvQueryID) references query (ID),
	foreign key(ssQueryID) references query (ID)
);

-- DROP PROCEDURE IF EXISTS add_index;
-- CREATE PROCEDURE add_index()
-- BEGIN
-- DECLARE  target_database VARCHAR(100);
-- DECLARE  target_table_name VARCHAR(100);
-- DECLARE  target_column_name VARCHAR(100);
-- DECLARE  target_index_name VARCHAR(100);
-- set target_table_name = 'user_info';
-- set target_index_name = 'user_index';
-- SELECT DATABASE() INTO target_database;
-- IF NOT EXISTS (SELECT * FROM information_schema.statistics WHERE table_schema = target_database AND table_name = target_table_name AND index_name = target_index_name) THEN
--     set @statement = "alter table `user_info` add UNIQUE KEY user_index (userID, shipID)";
--     PREPARE STMT FROM @statement;
--     EXECUTE STMT;
-- END IF;
-- END;
-- CALL add_index();

-- DROP PROCEDURE IF EXISTS add_index;
-- CREATE PROCEDURE add_index()
-- BEGIN
-- DECLARE  target_database VARCHAR(100);
-- DECLARE  target_table_name VARCHAR(100);
-- DECLARE  target_column_name VARCHAR(100);
-- DECLARE  target_index_name VARCHAR(100);
-- set target_table_name = 'query';
-- set target_index_name = 'query_index';
-- SELECT DATABASE() INTO target_database;
-- IF NOT EXISTS (SELECT * FROM information_schema.statistics WHERE table_schema = target_database AND table_name = target_table_name AND index_name = target_index_name) THEN
--     set @statement = "alter table `query` add UNIQUE KEY query_index (ID)";
--     PREPARE STMT FROM @statement;
--     EXECUTE STMT;
-- END IF;
-- END;
-- CALL add_index();
