"""One-shot GI AT-SPI worker. Input/output JSON only. Never logs UI contents."""
import json
import sys
import time
from linux_errors import reason_code


def run(req, Atspi):
    profile = json.load(open(req['profile'], encoding='utf-8'))
    def children(node):
        return [node.get_child_at_index(i) for i in range(node.get_child_count())]
    def walk(node, depth=0):
        if depth > 30:
            raise RuntimeError('tree depth limit')
        yield node
        for child in children(node):
            if child:
                yield from walk(child, depth + 1)
    def matches(node, spec):
        return (node.get_role_name() == spec['role'] and
                (spec.get('name') is None or node.get_name() == spec['name']) and
                (spec.get('description') is None or node.get_description() == spec['description']))
    def unique(nodes):
        nodes = list(nodes)
        if len(nodes) != 1:
            raise RuntimeError('missing or ambiguous accessible element')
        return nodes[0]
    # Only enumerate application names; descend solely into the configured Viber app.
    app = unique(n for n in children(Atspi.get_desktop(0)) if n.get_name() == profile['application'])
    window = unique(n for n in children(app) if matches(n, profile['window']))
    def select(key):
        node = window
        # Each path segment must match a unique direct child: never global fuzzy labels.
        for spec in profile['selectors'][key]:
            node = unique(n for n in children(node) if matches(n, spec))
        return node
    def text(node):
        interface = node.get_text_iface()
        if interface is None:
            raise RuntimeError('text interface required')
        return Atspi.Text.get_text(interface, 0, Atspi.Text.get_character_count(interface))
    def write(node, value):
        if not showing(node):
            raise RuntimeError('editable target not visible')
        edit = node.get_editable_text_iface()
        if edit is None or not edit.set_text_contents(value):
            raise RuntimeError('editable text unsupported')
        if text(node) != value:
            raise RuntimeError('Unicode readback mismatch')
    def showing(node):
        states = node.get_state_set()
        return states.contains(Atspi.StateType.SHOWING) and states.contains(Atspi.StateType.VISIBLE)
    def activate(node):
        if not showing(node) or not node.get_state_set().contains(Atspi.StateType.ENABLED):
            raise RuntimeError('action target not visible/enabled')
        iface = node.get_action_iface()
        if iface is None:
            raise RuntimeError('action interface required')
        names = [iface.get_action_name(i) for i in range(iface.get_n_actions())]
        indices = [i for i, name in enumerate(names) if name in ('click', 'activate', 'press')]
        if len(indices) != 1 or not iface.do_action(indices[0]):
            raise RuntimeError('unique accessible action required')
    def lines(node):
        values = []
        for child in walk(node):
            if not showing(child):
                continue
            try:
                value = text(child)
            except Exception:
                continue
            if value and value not in values:
                values.append(value)
        return values
    def identity():
        # Selector must target contact-details phone / independent self marker.
        node = select('identity')
        marker = profile.get('self_description')
        if marker and node.get_description() == marker:
            return 'self:my-notes'
        return text(node)
    def verify_current():
        if not req.get('recipient') or identity() != req['recipient']:
            raise RuntimeError('recipient changed or absent')
    action = req['action']
    if action == 'identity': return identity()
    if action == 'draft': return text(select('composer'))
    if action == 'write':
        verify_current()
        node = select('composer')
        old = text(node)
        if old and old != req['text']:
            raise RuntimeError('draft protected')
        write(node, req['text'])
        verify_current()
        return True
    if action == 'send':
        verify_current()
        if text(select('composer')) != req['text']:
            raise RuntimeError('draft changed before send')
        activate(select('send'))
        return True
    if action == 'read':
        result = lines(select(req['region']))
        return {'lines': result, 'line_count': len(result), 'text': '\n'.join(result), 'source': 'atspi'}
    if action == 'messages':
        result = []
        for node in children(select('conversation')):
            if showing(node) and matches(node, profile['outgoing_message']):
                attrs = node.get_attributes()
                # Require a stable application message identifier, never position/count alone.
                mid = attrs.get(profile.get('message_id_attribute', 'message-id'))
                if mid:
                    result.append({'id': mid, 'text': text(node), 'outgoing': True})
        return result
    if action == 'navigate':
        search = select('search')
        old = text(search)
        try:
            write(search, req['query'])
            deadline = time.monotonic() + 3
            while True:
                rows = [n for n in children(select('results')) if showing(n) and n.get_name() == req['query']]
                if len(rows) == 1:
                    activate(rows[0])
                    return {'matched': req['query'], 'low_confidence': False}
                if len(rows) > 1 or time.monotonic() > deadline:
                    raise RuntimeError('ambiguous or absent exact search result')
                time.sleep(.1)
        finally:
            write(search, old)
    raise RuntimeError('unknown operation')


if __name__ == '__main__':
    try:
        import gi
        gi.require_version('Atspi', '2.0')
        from gi.repository import Atspi
        print(json.dumps({'result': run(json.load(sys.stdin), Atspi)}, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error': reason_code(error)}))
