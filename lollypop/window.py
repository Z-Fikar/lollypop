#!/usr/bin/python
# Copyright (c) 2014 Cedric Bellegarde <gnumdk@gmail.com>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
# Many code inspiration from gnome-music at the GNOME project

from gi.repository import Gtk, Gdk, Gio, GLib, Tracker
from gettext import gettext as _, ngettext

from lollypop.collectionscanner import CollectionScanner
from lollypop.toolbar import Toolbar
from lollypop.database import Database
from lollypop.selectionlist import SelectionList
from lollypop.player import Player
from lollypop.view import *

class Window(Gtk.ApplicationWindow):

	"""
		Init window objects
	"""
	def __init__(self, app, db, player):
		Gtk.ApplicationWindow.__init__(self,
					       application=app,
					       title=_("Lollypop"))
		
		self._db = db
		self._player = player
		self._scanner = CollectionScanner()
		self._settings = Gio.Settings.new('org.gnome.Lollypop')

		self._artist_signal_id = 0

		self._setup_window()				
		self._setup_view()
		self._setup_media_keys()

		self.connect("map-event", self._on_mapped_window)

	"""
		Setup media player keys
	"""
	def _setup_media_keys(self):
		self._proxy = Gio.DBusProxy.new_sync(Gio.bus_get_sync(Gio.BusType.SESSION, None),
											 Gio.DBusProxyFlags.NONE,
											 None,
											 'org.gnome.SettingsDaemon',
											 '/org/gnome/SettingsDaemon/MediaKeys',
											 'org.gnome.SettingsDaemon.MediaKeys',
											 None)
		self._grab_media_player_keys()
		try:
			self._proxy.connect('g-signal', self._handle_media_keys)
		except GLib.GError:
            # We cannot grab media keys if no settings daemon is running
			pass

	"""
		Do key grabbing
	"""
	def _grab_media_player_keys(self):
		try:
			self._proxy.call_sync('GrabMediaPlayerKeys',
								 GLib.Variant('(su)', ('Lollypop', 0)),
								 Gio.DBusCallFlags.NONE,
								 -1,
								 None)
		except GLib.GError:
			# We cannot grab media keys if no settings daemon is running
			pass

	"""
		Do player actions in response to media key pressed
	"""
	def _handle_media_keys(self, proxy, sender, signal, parameters):
		if signal != 'MediaPlayerKeyPressed':
			print('Received an unexpected signal \'%s\' from media player'.format(signal))
			return
		response = parameters.get_child_value(1).get_string()
		if 'Play' in response:
			self._player.play_pause()
		elif 'Stop' in response:
			self._player.stop()
		elif 'Next' in response:
			self._player.next()
		elif 'Previous' in response:
			self._player.prev()
	
	"""
		Setup window icon, position and size, callback for updating this values
	"""
	def _setup_window(self):
		self.set_size_request(200, 100)
		self.set_icon_name('lollypop')
		size_setting = self._settings.get_value('window-size')
		if isinstance(size_setting[0], int) and isinstance(size_setting[1], int):
			self.resize(size_setting[0], size_setting[1])

		position_setting = self._settings.get_value('window-position')
		if len(position_setting) == 2 \
			and isinstance(position_setting[0], int) \
			and isinstance(position_setting[1], int):
			self.move(position_setting[0], position_setting[1])

		if self._settings.get_value('window-maximized'):
			self.maximize()

		self.connect("window-state-event", self._on_window_state_event)
		self.connect("configure-event", self._on_configure_event)

	"""
		Setup window main view:
			- genre list
			- artist list
			- main view as artist view or album view
	"""
	def _setup_view(self):
		self._box = Gtk.Grid()
		self.toolbar = Toolbar(self._db, self._player)
		self.set_titlebar(self.toolbar.header_bar)
		self.toolbar.header_bar.show()
		self.toolbar.get_infobox().connect("button-press-event", self._show_current_album)

		self._list_genres = SelectionList("Genre", 150)
		self._list_artists = SelectionList("Artist", 200)
		
		self._view = LoadingView()

		separator = Gtk.Separator()
		separator.show()
		self._box.add(self._list_genres.widget)
		self._box.add(separator)
		self._box.add(self._list_artists.widget)
		self._box.add(self._view)
		self.add(self._box)
		self._box.show()
		self.show()
	
	"""
		Run collection update on mapped window
		Pass _update_genre() as collection scanned callback
	"""	
	def _on_mapped_window(self, obj, data):
		self._scanner.update(self._update_genres)
		
	"""
		Update genres list with genres
	"""
	def _update_genres(self, genres):
		self._list_genres.populate(genres)
		self._list_genres.connect('item-selected', self._update_artists)
		self._list_genres.widget.show()
		self._box.remove(self._view)
		self._view = AlbumView(self._db, self._player, None)
		self._box.add(self._view)
		self._view.populate_popular()

	"""
		Update artist list for genre_id
	"""
	def _update_artists(self, obj, genre_id):
		if self._artist_signal_id:
			self._list_artists.disconnect(self._artist_signal_id)
		self._list_artists.populate(self._db.get_artists_by_genre_id(genre_id))
		self._artist_signal_id = self._list_artists.connect('item-selected', self._update_view_artist)
		self._list_artists.widget.show()
		self._update_view_albums(self, genre_id)
		self._genre_id = genre_id

	"""
		Update artist view for artist_id
	"""
	def _update_view_artist(self, obj, artist_id):
		self._box.remove(self._view)
		self._view = ArtistView(self._db, self._player, self._genre_id, artist_id)
		self._box.add(self._view)
		self._view.populate()
	
	"""
		Update albums view for genre_id
	"""
	def _update_view_albums(self, obj, genre_id):
		self._box.remove(self._view)
		self._view = AlbumView(self._db, self._player, genre_id)
		self._box.add(self._view)
		self._view.populate()
	
	"""
		Save new window size/position
	"""		
	def _on_configure_event(self, widget, event):
		size = widget.get_size()
		self._settings.set_value('window-size', GLib.Variant('ai', [size[0], size[1]]))

		position = widget.get_position()
		self._settings.set_value('window-position', GLib.Variant('ai', [position[0], position[1]]))

	"""
		Save maximised state
	"""
	def _on_window_state_event(self, widget, event):
		self._settings.set_boolean('window-maximized', 'GDK_WINDOW_STATE_MAXIMIZED' in event.new_window_state.value_names)

	"""
		Show current album context/content
	"""
	def _show_current_album(self, obj, data):
		if self._player.get_current_track_id() != -1:
			self._view.update_context()
			self._view.update_content()
