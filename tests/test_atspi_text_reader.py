from types import SimpleNamespace
import pytest
from atspi_text_reader import read_text


class Node:
    def __init__(self, name='', role='filler', children=(), box=(0, 0, 100, 100), text=None, visible=True, pid=42):
        self.name, self.role, self.children, self.box = name, role, list(children), box
        self.value, self.visible, self.pid, self.reads = text, visible, pid, 0
    def get_child_count(self): return len(self.children)
    def get_child_at_index(self, i): return self.children[i]
    def get_name(self): return self.name
    def get_role_name(self): return self.role
    def get_process_id(self): return self.pid
    def get_interfaces(self): return ['Text'] if self.value is not None else []
    def get_component_iface(self): return self
    def get_extents(self, coords):
        return SimpleNamespace(**dict(zip(('x', 'y', 'width', 'height'), self.box)))
    def get_state_set(self): return self
    def contains(self, state): return self.visible
    def get_text_iface(self): return self
    def get_character_count(self): return len(self.value)
    def get_text(self, start, end): self.reads += 1; return self.value[start:end]


def fixture(extra=()):
    unrelated = Node(text='Private unrelated message', box=(0, 0, 100, 20))
    composer = Node(text='Привіт 👋\nТочний текст', box=(0, 80, 100, 20))
    frame = Node(name='Rakuten Viber', role='frame', children=[unrelated, composer, *extra])
    app = Node(name='ViberPC', children=[frame])
    root = Node(children=[app])
    atspi = SimpleNamespace(get_desktop=lambda index: root, set_timeout=lambda *a: None,
                            CoordType=SimpleNamespace(SCREEN=0),
                            Text=SimpleNamespace(get_text=lambda node,start,end: node.get_text(start,end),
                                                 get_character_count=lambda node: node.get_character_count()),
                            StateType=SimpleNamespace(SHOWING=1, VISIBLE=2))
    req = {'application': 'ViberPC', 'window': 'Rakuten Viber', 'pid': 42,
           'geometry': [0, 0, 100, 100], 'point': [50, 90]}
    return req, atspi, composer, unrelated


def test_native_read_is_exact_and_scoped_to_composer():
    req, atspi, composer, unrelated = fixture()
    assert read_text(req, atspi) == composer.value
    assert composer.reads == 1 and unrelated.reads == 0


@pytest.mark.parametrize('key,value', [('pid', 99), ('geometry', [0, 0, 101, 100]), ('point', [150, 150])])
def test_wrong_process_geometry_or_point_never_reads_text(key, value):
    req, atspi, composer, unrelated = fixture()
    req[key] = value
    with pytest.raises(ValueError): read_text(req, atspi)
    assert composer.reads == unrelated.reads == 0


def test_ambiguous_overlapping_text_rejected_before_read():
    other = Node(text='Other editor', box=(0, 80, 100, 20))
    req, atspi, composer, unrelated = fixture([other])
    with pytest.raises(ValueError): read_text(req, atspi)
    assert other.reads == composer.reads == unrelated.reads == 0


def test_hidden_or_oversized_composer_rejected():
    req, atspi, composer, unrelated = fixture()
    composer.visible = False
    with pytest.raises(ValueError): read_text(req, atspi)
    assert composer.reads == 0
    composer.visible = True
    composer.value = 'x' * 20001
    with pytest.raises(ValueError): read_text(req, atspi)
    assert composer.reads == unrelated.reads == 0
