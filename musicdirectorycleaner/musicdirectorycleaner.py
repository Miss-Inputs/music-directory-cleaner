import cProfile
import magic #https://pypi.python.org/pypi/python-magic (MIT)
import mimetypes
import os
import os.path
import re
import shutil
import sqlite3
import taglib #https://pypi.python.org/pypi/pytaglib (GPLv3)
from gi.repository import GLib #PyGObject (LGPL)
from os.path import expanduser


def check_access(music_folder):
	#TODO: Sometimes there are cases like * characters in filenames on CIFS filesystems that say
	#the file exists here, but when you try and read it with anything else later, it says it doesn't
	#exist (because it shouldn't exist with that filename). Should handle that here somehow
	#Maybe instead of using os.access we should actually try and read the file? That's dumb but
	#it'll work
	#FIXME Actually yeah this doesn't seem to work at all
	for root, folders, files in os.walk(music_folder):
		all_good_in_the_hood = True
		for folder in folders:
			if folder.startswith('.Trash-'):
				#If it's a network share, Linux will put this here for the recycle bin. We don't care about that
				continue
			folder_path = os.path.join(root, folder)
			if not os.access(folder_path, os.R_OK | os.W_OK | os.X_OK):
				all_good_in_the_hood = False
				print(folder_path)
		for f in files:
			file_path = os.path.join(root, f)
			if not os.access(file_path, os.R_OK | os.W_OK):
				all_good_in_the_hood = False
				print(file_path)
	if all_good_in_the_hood:
		print('Nice')
		
def check_mime_type(path):
	mime_type = magic.detect_from_filename(path).mime_type
	if mime_type == 'application/octet-stream':
		#Sometimes file is dumb, so we have to check the extension instead of content
		mime_type = mimetypes.guess_type(path)[0]
	return mime_type

def is_audio_file(path):
	#This is too slow and I'm lazy so let's just use a quick and dirty method here
	ext = os.path.splitext(path)[1]
	return ext in ('.ogg', '.mp3', '.flac', '.m4a', '.wma')

	mime_type = check_mime_type(path)
	if mime_type is not None and mime_type.startswith('audio/'):
		return True
	if mime_type == 'video/x-ms-asf':
		#Listen here you little shit
		return True
	return False
				
def check_empty_folders(music_folder, dryRun=True):
	for root, folders, ignored in os.walk(music_folder, topdown=False):
		for f in folders:
			try:
				if f.startswith('.Trash-') or root.startswith(os.path.join(music_folder, '.Trash-')):
					continue
				folder = os.path.join(root, f)
				#Because I'm using the iterator twice, I'll need to save it as a list, otherwise
				#it'll run out the first time I use it. I'm an idiot and don't realise things like this
				files = list(os.scandir(folder))
				
				if len(list(f for f in files if f.is_dir())):
					#Contains subfolders, therefore not really empty
					continue
						
				actual_files = [f for f in files if f.is_file()]
				contains_music_files = False
				for f in actual_files:
					if is_audio_file(f.path):
						contains_music_files = True
						break
				if not contains_music_files:
					print(folder, [f.name for f in actual_files])
					
				if not dryRun and len(actual_files) == 0:
					os.rmdir(folder)
			except Exception as e:
				print('Shitting titwanks', e, f, folder)
				
def path_to_uri(path):
	#Python's pathname2url doesn't work in quite the same way that Banshee works (the latter
	#doesn't encode & or ' for example), so we're using glib to do it since that's what Banshee
	#ultimately uses
	return GLib.filename_to_uri(path)
				
def get_db(readonly=True):	
	banshee_db_path = '{0}/.config/banshee-1/banshee.db'.format(expanduser('~'))
	path = 'file:{0}?mode={1}'.format(banshee_db_path, 'ro' if readonly else 'rw')
	conn = sqlite3.connect(path, uri=True)
	return conn
				
db = get_db(readonly=False)
def is_in_banshee_library(path):
	#db = get_db()
	uri = path_to_uri(path)
	return row_exists(db, 'SELECT 1 FROM coretracks WHERE Uri = ? AND primarysourceid = 1', uri)
	
def which_banshee_playlists(path):
	return query_onecol(db, 'SELECT name FROM coreplaylists WHERE playlistid IN (SELECT playlistid FROM coreplaylistentries WHERE trackid = (SELECT trackid FROM coretracks WHERE Uri = ? AND primarysourceid = 1))', path_to_uri(path))
	
def query(db, sql, * params):
	cursor = db.execute(sql, params)
	columns = [x[0] for x in cursor.description]
	
	return [dict(zip(columns, row)) for row in cursor]

def query_onecol(db, sql, * params):
	cursor = db.execute(sql, params)
	return [row[0] for row in cursor]

def query_first(db, sql, * params):
	cursor = db.execute(sql, params)
	columns = [x[0] for x in cursor.description]
	row = cursor.fetchone()
	if row is None:
		return None

	return dict(zip(columns, row))

def row_exists(db, sql, * params):
	cursor = db.execute(sql, params)
	return cursor.fetchone() is not None
				
def check_music_files_are_in_banshee(music_folder):
	for root, folders, files in os.walk(music_folder):
		for f in files:
			file_path = os.path.join(root, f)
			if is_audio_file(file_path) and not is_in_banshee_library(file_path):
				print(file_path)
				
def replace_chars(s):
	replacements = {
	'"': "'",
	'*': '_',
	'/': '-',
	#':': ' -',
	'<': '_',
	'>': '_',
	'?': '',
	'|': '_'
	}
	for k in replacements:
		s = s.replace(k, replacements[k])
	
	#: is an illegal character, but to look nice, we replace stuff like "Foo: The Bar" with
	#"Foo - The Bar". This doesn't really work if the : isn't for
	#punctuation, so if it's not succeeded by a space, just replace it with _
	#s = re.sub('(?<= ):', ' -', s)
	s = s.replace(': ', ' - ')
	s = s.replace(':', '_')
	
	if s.startswith('.'):
		#While legal for a filename, many music players will ignore hidden directories/files
		s = s.lstrip('.')
		
	if s.endswith('.'):
		#This replacement isn't strictly necessary unlike the others, but it just looks nice
		#TODO: Should "aaa...?" be replaced with "aaa..._" or "aaa"?
		s = s.rstrip('.')
	return s

def get_album_artist(tags):
	if 'ALBUMARTIST' in tags:
		return tags['ALBUMARTIST'][0]
	else:
		if 'ARTIST' in tags:
			print('This has artist but no album artist: ', tags)
			return tags['ARTIST'][0]
		else:
			return 'Unknown Artist'

def get_album(tags):
	if 'ALBUM' in tags:
		return tags['ALBUM'][0]
	else:
		return 'Unknown Album'
	
def get_track_number(tags):
	if 'TRACKNUMBER' in tags:
		track_number = tags['TRACKNUMBER'][0]
		if '/' in track_number:
			return int(track_number.split('/')[0])
		else:
			return int(track_number)
	else:
		return None

def get_disc_number(tags):
	if 'DISCNUMBER' in tags:
		disc_number = tags['DISCNUMBER'][0]
		if '/' in disc_number:
			return int(disc_number.split('/')[0])
		else:
			return int(disc_number)
	else:
		return None
				
def calculate_new_path(music_file):
	tags = taglib.File(music_file).tags
	
	album_artist = get_album_artist(tags)
	album = get_album(tags)
		
	new_folder = os.path.join(music_folder, replace_chars(album_artist), replace_chars(album))
	
	extension = os.path.splitext(music_file)[1].lower()
	if 'TITLE' in tags:
		title = replace_chars(tags['TITLE'][0])
	else:
		print('What the hell?', music_file)
		title = 'Unknown Title'
	
	track_number = get_track_number(tags)
	if track_number is not None:
		
		disc_number = get_disc_number(tags)
		if disc_number is not None:
			new_name = '{0}-{1:02d} - {2}{3}'.format(disc_number, track_number, title, extension)
		else:
			new_name = '{0:02d} - {1}{2}'.format(track_number, title, extension)
	else:
		new_name = title + extension
	return (new_folder, new_name)

def update_uri_in_banshee(old_path, new_path):
	sql = 'UPDATE coretracks SET uri = ? WHERE uri = ? AND primarysourceid = 1'
	return db.execute(sql, (path_to_uri(new_path), path_to_uri(old_path))).rowcount
				
def move_music_file(old_path, new_folder, new_filename, dryRun=True):
	new_path = os.path.join(new_folder, new_filename)
	if dryRun:
		print(old_path)
		print(new_path)
		print('---')
		return
	
	#This was just here for debugging, but I find it useful for reassurance that if something goes
	#horribly wrong updating the Banshee library and I have to re-add the song again, I can
	#put it back in the playlists that it was in
	print(old_path, ' is in ', which_banshee_playlists(old_path))
	
	os.makedirs(new_folder, exist_ok=True)
	shutil.move(old_path, new_path)
	print('Moved ', old_path, ' to ', new_path)
	
	rows = update_uri_in_banshee(old_path, new_path)
	print('Result of updating Banshee DB: ', rows)
		
	print('---')
				
def move_files_around(music_folder, dryRun=True):
	for root, folders, files in os.walk(music_folder):
		for f in files:
			#if root.startswith(os.path.join(music_folder, 'A')):
			#	return
			try:
				file_path = os.path.join(root, f)
				if is_audio_file(file_path):
					new_folder, new_filename = calculate_new_path(file_path)
					new_path = os.path.join(new_folder, new_filename)
					if new_path != file_path:
						move_music_file(file_path, new_folder, new_filename, dryRun)
			except Exception as e:
				print('What the dicks', f, e)
				
def main(music_folder):
	#check_access(music_folder)
	#check_empty_folders(music_folder, False)
	#print(is_in_banshee_library('/home/megan/Music/石川智晶/Boku ha Mada Nani mo Shiranai/03 - Uninstall.mp3'))
	#print(path_to_uri("/home/megan/Music/'Weird Al' Yankovic & Wendy Carlos/Peter and the Wolf/08 - The Carnival of the Animals, Part Two_ Amoeba.mp3"))
	check_music_files_are_in_banshee(music_folder)
	#ove_files_around(music_folder, False)
	
if __name__ == "__main__":
	music_folder = expanduser('~/Music')
	#main(music_folder)
	cProfile.run("main(music_folder)")
