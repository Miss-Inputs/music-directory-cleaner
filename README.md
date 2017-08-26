# music-directory-cleaner

For those of us who like to store our music on our own dang computers, this helps us make sure everything is in order. It can check that files are accessible/writeable, check for folders that don't actually contain any music files, and perhaps most usefully it can move music files around according to their tags so you have everything in nice consistent folders and whatnot. Currently, it hardcodes a pattern for doing this, though in future this could be specified by the user.

It also integrates with Banshee media player, e.g. detecting songs that aren't in the Banshee database but could be imported. When moving files around, it should update the Banshee database as well to make sure that it all happens seamlessly and Banshee doesn't complain about missing files and you have to add stuff to your playlists again. However, that feature isn't tested enough, so I wouldn't trust it.

Because I just developed this and I'm lazy, it doesn't really have a CLI or GUI of any kind, you just sort of call the function you want within main(). That's not so user friendly, but it's all I have for now.

Needs pytaglib, python-magic, and PyGObject to do all the things.
Probably needs python3, because it was developed with that. Might run under Python 2, but I haven't tried.