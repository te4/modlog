#!/usr/bin/env python
import re
import sys
import yaml
import json
import sqlite3
import MySQLdb
from itertools import chain
from datetime import datetime
from repoze.lru import lru_cache
from breve import Template
from breve.tags.html import tags
from materials import materials

'''This is mostly undocumented, not especially modular and was only ever intended for personal use. It's broken? Your problem now.'''

'''TODO
[ ] show different commands for mods and modaccounts
[x] commands by time
[x] chest accesses by time
[x] list owners of accessed chests
[x] support nether and end
[x] show removed protections
[ ] log protection changes
[x] block changes by time (summed up)
[x] block changes by coords (summed up)
[x] block changes by blocktypes
[?] chest accesses by blocktypes
[x] cronjob
[ ] table macros
'''

'''queries the db for user actions and returns a number of readily formated tr elements'''
def listExecutedCommands (nick):
	c = logblock.cursor()
	c.execute('''select date,message from `lb-chat` join `lb-players` using (playerid) where date >= %s and date < date_add(%s, interval 1 day) and message like '/%%' and message not like '/tell%%' and playername = %s order by date''', ( day, day, nick ))
	rows = [ (normalizeId('command', nick, date), isBoring(command), date, command) for (date, command) in c.fetchall() ]
	return [(date, tags.tr (id = commandId, class_ = boring) [
		[tags.td [s] for s in [ tags.a ( href = '#' + commandId ) [ '#' ], date, 'command']], [ tags.td (colspan = '4') [ command ] ]
	]) for (commandId, boring, date, command) in rows]

def queryChestAccesses (world, nick):
	c = logblock.cursor()
	c.execute('''select date,itemamount,itemtype,itemdata,type,x,y,z from `lb-players` inner join (`lb-%s-chest` left join `lb-%s` using (id)) using (playerid) where date >= %%s and date < date_add(%%s, interval 1 day) and playername = %%s order by date''' % (world, world), (day, day, nick))
	return c.fetchall()

worldnames = { 'int':'int', 'int_nether':'nether', 'int_the_end':'end' }
renders = { 'int':0, 'int_nether':3, 'int_the_end':6 }
def listChestAccesses (nick):
	accesses = list(chain(*[[ row + (world,) for row in queryChestAccesses(world, nick) ] for world in worldnames.keys()]))
	rows = [ (normalizeId('access', nick, date), date, iamount, ( materials[itype] or 'unknown (%s)' % itype ) + (' (%s)' % idata if idata else '' ), getProtectionOwner(ctype,world,x,y,z) or getPastProtectionOwner(x, y, z) , '%s/%s/%s' % (x,y,z), renders[world], worldnames[world] ) for (date,iamount,itype,idata,ctype,x,y,z,world) in accesses]
	return [(date, tags.tr (id = rowId) [
		[tags.td[s] for s in [ tags.a ( href = '#' + rowId ) [ '#' ], date, 'chest', amount, material, tags.a (href = 'http://mc.dev-urandom.eu/map/#/%s/-2/%s/0' % (pos, render)) [ worldname, '/', pos ], owner ] ]
	]) for (rowId, date, amount, material, owner, pos, render, worldname) in rows]

def listBlockChanges (nick):
	c = logblock.cursor()
	query = '''select date_add(date(date), interval hour(date) hour),sum(created),sum(destroyed) from (''' + ' union all '.join(['''(select date,type != 0 as created,replaced != 0 as destroyed from `lb-%s` join `lb-players` using (playerid) where date >= %%s and date < date_add(%%s, interval 1 day) and playername = %%s and type != replaced )''' % world for world in worldnames.keys()]) + ''') as blockchanges group by hour(date)'''
	c.execute(query, (day, day, nick) * len(worldnames))
	rows = [( normalizeId('blocks', nick, date), date, created, destroyed) for (date, created, destroyed) in c.fetchall()]
	return [(date, tags.tr (id = rowId) [
		tags.td [ tags.a (href = '#' + rowId) [ '#' ] ],
		tags.td [ date ],
		tags.td [ 'blocks/hour' ],
		tags.td (colspan = '4') [ 'Placed: %s, ' % created if created else '', 'Destroyed: %s' % destroyed if destroyed else '' ]
	]) for (rowId, date, created, destroyed) in rows]

'''TODO'''
def listProtectionChanges (nick):
	return []

def presentBlockchangesByArea (nick):
	c = logblock.cursor()
	c.execute('''select count(*) as count,world,round(x,-2) as x_,round(z,-2) as z_ from (''' + ' union all '.join(['''select '%s' as world, x, z from `lb-%s` join `lb-players` using (playerid) where date >= %%s and date < date_add(%%s, interval 1 day) and playername = %%s and type != replaced''' % (world, world) for world in worldnames.keys()]) + ''') as foo group by world,x_,z_ order by world,count desc''', (day, day, nick) * len(worldnames))
	rows = [( normalizeId('area', nick, x, z), count, world, x, z) for (count, world, x, z) in c.fetchall()]
	return [tags.tr (id = rowId) [
		tags.td [ tags.a (href = '#' + rowId) [ '#' ] ],
		tags.td [ 'block changes' ],
		tags.td [ count ],
		tags.td [ '~ ', tags.a (href = 'http://mc.dev-urandom.eu/map/#/%s/64/%s/-2/%s/0' % (x, z, renders[world])) [ '%s/%s/*/%s' % (worldnames[world], x, z) ] ]
	] for (rowId, count, world, x, z) in rows]

def presentBlockchangesByMaterial (nick):
	c = logblock.cursor()
	query = '''select sum(count) as net, type from (''' + ' union all '.join([('''(select -count(*) as count,replaced as type from `lb-%s` join `lb-players` using (playerid) where date >= %%s and date < date_add(%%s, interval 1 day) and playername = %%s group by replaced) union all (select count(*) as count,type from `lb-%s` join `lb-players` using (playerid) where date >= %%s and date < date_add(%%s, interval 1 day) and playername = %%s group by type)''' ) % (world, world) for world in worldnames.keys()]) + ''') as accumulatedchanges where type != 0 group by type order by net'''
	c.execute(query, (day, day, nick) * len(worldnames) * 2)
	rows = [(normalizeId('blocks.hour', nick, materials[btype], day), net, materials[btype]) for (net, btype) in c.fetchall() if net]
	return [tags.tr (id = rowId) [
		tags.td [ tags.a (href = '#' + rowId) [ '#' ] ],
		tags.td [ 'placed' if net > 0 else 'destroyed' ],
		tags.td [ abs(net) ],
		tags.td [ material ]
	] for (rowId, net, material) in rows]

'''relatively useless but I'll leave it here'''
def presentChestAccessesByMaterial (nick):
	c = logblock.cursor()
	query = '''select itemtype,itemdata,sum(itemamount) as amount from (''' + ' union all '.join(['''(select itemtype,itemdata,itemamount from (`lb-%s` join `lb-%s-chest` using (id)) join `lb-players` using (playerid) where date >= %%s and date < date_add(%%s, interval 1 day) and playername = %%s)''' % (world, world) for world in worldnames.keys()]) + ''') group by itemtype,itemdata order by amount'''

@lru_cache(maxsize=500)
def getProtectionOwner (ctype, world, x, y, z):
	lwcc = lwc.cursor()
	protection = lwcc.execute('select owner,data from lwc_protections where blockId = ? and world = ? and x = ? and y = ? and z = ? group by owner,data,blockId,world,x,y,z', (ctype, world, x, y, z)).fetchall()
	if not len(protection):
		protection = lwcc.execute('select owner,data from lwc_protections where blockId = ? and world = ? and y = ? and (abs( ? - x ) <= 1 and z = ? or x = ? and abs( ? - z ) <= 1) group by owner,data,blockId,world,x,y,z', (ctype, world, y, x, z, x, z)).fetchall()
	return ' or '.join(map(formatProtection, protection))

def formatProtection (protection):
	owner = protection[0]
	access = ', '.join([player for player in [entry['name'] for entry in json.loads(protection[1])['rights']] if not player == owner] if protection[1] else [])
	return 'Owner: %s' % (owner) + (' (Access: %s)' % access) if access else ''

@lru_cache(maxsize=500)
def getPastProtectionOwner (x,y,z):
	lwcc = lwc.cursor()
	protection = lwcc.execute('select metadata from lwc_history where status = 1 and x = ? and y = ? and z = ? group by player,x,y,z,type,status,metadata', (x, y, z)).fetchall()
	if not len(protection):
		protection = lwcc.execute('select metadata from lwc_history where status = 1 and y = ? and (abs( ? - x ) <= 1 and z = ? or x = ? and abs( ? - z ) <= 1) group by player,x,y,z,type,status,metadata', (y, x, z, x, z)).fetchall()
	return 'destroyed; ' + ' or '.join(map(formatPastProtection, protection)) if protection else 'unprotected?'

def formatPastProtection (protection):
	metadata = dict([s.split('=') for s in protection[0].split(',') if s])
	return 'Creator: %s' % (metadata['creator']) + (', Destroyer: %s' % metadata['destroyer']) if 'destroyer' in metadata else ''

def normalizeId (*args):
	return re.sub(r'[- :]', '_', '_'.join(map(str, args)))

def aggregate (*groups):
	intermediate = list(chain(*groups))
	intermediate.sort()
	return [tr for (date, tr) in intermediate]

def collectActivity (nick):
	activity = aggregate(
		listExecutedCommands(nick),
		listChestAccesses(nick),
		listBlockChanges(nick),
		listProtectionChanges(nick),
	)
	materials = presentBlockchangesByMaterial(nick)
	hotspots = presentBlockchangesByArea(nick)
	return [
		tags.h2 ( id = nick ) [ nick , ' ', tags.a ( class_ = 'hashlink', href = '#'+nick ) [ '#' ] ],
		tags.h3 [ 'activity by time' ] if activity else '',
		tags.table (class_ = 'bytime') [ activity ] if activity else '',
		tags.h3 [ 'materials used (net)' ] if materials else '',
		tags.table (class_ = 'bymaterial') [ materials ] if materials else '',
		tags.h3 [ 'activity by area' ] if hotspots else '',
		tags.table (class_ = 'byarea') [ hotspots ] if hotspots else '',
		] if activity or materials or hotspots else []

boringtester = re.compile('^/(v$|vanish$|lag$|warp|lb tb?$|lb tb? off$|spawn|tp .*)')
def isBoring (s):
	return 'boring' if boringtester.search(s) else ''

logblock = MySQLdb.connect(
	host = 'localhost',
	port = 53306,
	user = 'xxxxxxx',
	passwd = 'xxxxxxx',
	db = 'minecraft'
)
lwc = sqlite3.connect('/home/mc/backup/plugins/LWC/lwc.db')

f = open('/home/mc/backup/plugins/PermissionsBukkit/config.yml', 'r')
data = yaml.safe_load(f)
f.close()

modaccounts = [u[0] for u in dict.items(data['users']) if 'modaccount' in u[1]['groups'] ]
moderators = [u[0] for u in dict.items(data['users']) if 'moderator' in u[1]['groups'] ]

day = sys.argv[1]

t = Template ( tags, root = '.' )
t.doctype = '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">'

vars = dict (
	day = day,
	players = map(collectActivity, modaccounts),
)


logblock.close()
lwc.close()

print t.render ( 'index', vars )
