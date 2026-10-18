"""Synthetic GTK desktop fixture. Never Viber, no network or messaging."""
import gi
import json
import sys
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, Atk

w=Gtk.Window(title='Synthetic Viber MCP Fixture')
w.get_accessible().set_name('Synthetic Fixture')
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
w.add(box)

def entry(name,value=''):
    e=Gtk.Entry();e.set_text(value);e.get_accessible().set_name(name);box.pack_start(e,False,False,0);return e
identity=entry('Identity','2025550123')
composer=Gtk.TextView();composer.get_accessible().set_name('Composer');box.pack_start(composer,False,False,0)
search=entry('Search')
results=Gtk.Box();results.get_accessible().set_name('Results');box.pack_start(results,False,False,0)
row=Gtk.Button(label='2025550123');results.pack_start(row,False,False,0)
conversation=Gtk.Box();conversation.get_accessible().set_name('Conversation');box.pack_start(conversation,False,False,0)
line=Gtk.TextView();line.get_buffer().set_text('SYNTHETIC conversation only');conversation.pack_start(line,False,False,0)
hidden=Gtk.TextView();hidden.get_buffer().set_text('HIDDEN MUST NOT BE READ');hidden.set_no_show_all(True);conversation.pack_start(hidden,False,False,0)
sidebar=Gtk.Box();sidebar.get_accessible().set_name('Sidebar');box.pack_start(sidebar,False,False,0)
preview=Gtk.Entry();preview.set_text('SYNTHETIC sidebar only');sidebar.pack_start(preview,False,False,0)
send=Gtk.Button(label='Synthetic Send');box.pack_start(send,False,False,0)
def sent(button):
    buf=composer.get_buffer()
    line.get_buffer().set_text(buf.get_text(buf.get_start_iter(),buf.get_end_iter(),True))
    buf.set_text('')
send.connect('clicked',sent)
w.connect('destroy',Gtk.main_quit)
w.show_all()
Gtk.main()
