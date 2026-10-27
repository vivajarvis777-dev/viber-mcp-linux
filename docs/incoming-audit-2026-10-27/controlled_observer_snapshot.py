"""Temporary passive observer; never imports Viber or invokes GUI/send methods."""
import argparse
import collections
import json
import os
import re
import time
import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

# Historical snapshot, not a repaired adapter. No raw payload capture.
parser = argparse.ArgumentParser(description='Historical observer; approved test window required')
parser.add_argument('--viber-pid', type=int, required=True)
parser.add_argument('--marker', required=True)
parser.add_argument('--expected-sender', required=True, help='Authorized test number, digits only')
parser.add_argument('--seconds', type=int, default=420)
options = parser.parse_args()
if options.viber_pid <= 0 or not 1 <= options.seconds <= 420 or not options.marker or not options.expected_sender.isdigit():
    parser.error('Invalid observation parameters')
PID = options.viber_pid
MARKER = options.marker
EXPECTED_SENDER = options.expected_sender
DURATION = options.seconds
DBusGMainLoop(set_as_default=True)
control = dbus.SessionBus(private=True)
daemon = dbus.Interface(control.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus'), 'org.freedesktop.DBus')
owners = set()
for name in daemon.ListNames():
    if not str(name).startswith(':'):
        continue
    try:
        if int(daemon.GetConnectionUnixProcessID(name)) == PID:
            owners.add(str(name))
    except dbus.DBusException:
        pass
if not owners:
    raise SystemExit('No Viber bus owners')

counts = collections.Counter()
started = time.monotonic()
def emit(record):
    print(json.dumps({'elapsed': round(time.monotonic()-started, 2), **record}), flush=True)

def marker_in(value):
    if isinstance(value, (str, dbus.String)):
        return MARKER in str(value)
    if isinstance(value, (list, tuple, dbus.Array)):
        return any(marker_in(v) for v in value)
    return False

monitor = dbus.SessionBus(private=True)
def observe(connection, message):
    iface, member, sender = message.get_interface(), message.get_member(), str(message.get_sender())
    if iface == 'org.freedesktop.DBus' and member == 'ListNames' and sender == control.get_unique_name():
        counts['diagnostic_bus_call'] += 1
        emit({'kind': 'monitor_delivery_verified'})
        return
    if sender not in owners:
        return
    if iface == 'org.freedesktop.Notifications' and member == 'Notify':
        counts['viber_notify'] += 1
        args = message.get_args_list()
        summary = str(args[3]) if len(args) > 3 else ''
        digits = ''.join(x for x in summary if x.isdigit())
        if len(digits) == 10 and digits.startswith('0'):
            digits = '38' + digits
        hints = args[6] if len(args) > 6 and isinstance(args[6], dict) else {}
        safe_keys = [str(k) for k in hints if re.fullmatch(r'[A-Za-z_.-]{1,80}', str(k))]
        emit({'kind': 'viber_notify', 'marker_present': marker_in(args[4]) if len(args)>4 else False,
              'summary_matches_test_phone': digits == EXPECTED_SENDER,
              'hint_keys': sorted(safe_keys), 'other_hint_key_count': len(hints)-len(safe_keys),
              'argument_types': [type(x).__name__ for x in args]})
    elif message.get_type() == dbus.lowlevel.MESSAGE_TYPE_SIGNAL:
        label = str(iface) + '.' + str(member)
        counts['session_signal:' + label] += 1
        if counts['session_signal:' + label] <= 3:
            emit({'kind': 'viber_session_signal', 'interface': iface, 'member': member})

monitor.add_message_filter(observe)
rules = ["type='method_call',interface='org.freedesktop.Notifications',member='Notify'",
         "type='method_call',interface='org.freedesktop.DBus',member='ListNames'"]
rules.extend("type='signal',sender='"+o+"'" for o in owners)
dbus.Interface(monitor.get_object('org.freedesktop.DBus','/org/freedesktop/DBus'),
               'org.freedesktop.DBus.Monitoring').BecomeMonitor(rules, dbus.UInt32(0))

a11y = None
registered = []
registry = None
try:
    address = control.get_object('org.a11y.Bus','/org/a11y/bus').GetAddress(dbus_interface='org.a11y.Bus')
    a11y = dbus.bus.BusConnection(str(address))
    root = a11y.get_object('org.a11y.atspi.Registry','/org/a11y/atspi/accessible/root')
    target = None
    for dest, path in root.GetChildren(dbus_interface='org.a11y.atspi.Accessible'):
        obj = a11y.get_object(dest, path)
        try:
            if str(obj.Get('org.a11y.atspi.Accessible','Name',dbus_interface='org.freedesktop.DBus.Properties')) == 'ViberPC':
                target = str(dest)
                break
        except dbus.DBusException:
            pass
    if target:
        def event(*args, **kw):
            if kw.get('sender') != target:
                return
            label = kw.get('interface','') + '.' + kw.get('member','')
            counts['atspi:' + label] += 1
            match = marker_in(args)
            if match:
                counts['atspi_marker_events'] += 1
            if match or counts['atspi:' + label] <= 3:
                emit({'kind':'atspi_event', 'interface':kw.get('interface'),
                      'member':kw.get('member'), 'marker_present':match,
                      'argument_types':[type(x).__name__ for x in args]})
        a11y.add_signal_receiver(event,sender_keyword='sender',interface_keyword='interface',member_keyword='member')
        registry = dbus.Interface(a11y.get_object('org.a11y.atspi.Registry','/org/a11y/atspi/registry'),'org.a11y.atspi.Registry')
        for name in ['object:text-changed','object:children-changed','object:property-change','window']:
            registry.RegisterEvent(name,dbus.Array([],signature='s'),target)
            registered.append(name)
    emit({'kind':'ready', 'observer_pid':os.getpid(), 'notify_monitor':True,
          'atspi_registered':len(registered), 'window_seconds':DURATION,
          'payloads_retained':False,'outbound_sender_present':False})
    loop = GLib.MainLoop()
    def verify():
        daemon.ListNames()
        return False
    GLib.idle_add(verify)
    GLib.timeout_add_seconds(DURATION,lambda:(loop.quit(),False)[1])
    loop.run()
    emit({'kind':'complete','counts':dict(counts),'payloads_retained':False})
finally:
    if registry:
        for name in registered:
            registry.DeregisterEvent(name)
    if a11y:
        a11y.close()
    monitor.close()
    control.close()
