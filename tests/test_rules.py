import pytest

from ai.rules import RuleEngine, normalize_for_rules
from conftest import ROOT, make_listing


@pytest.mark.parametrize("raw,expected", [
    ("alpr4 1mg buat tidur", "alpra 1mg buat tidur"),       # plesetan diubah, satuan dosis tetap
    ("Top up s-l-o-t gacor", "top up slot gacor"),          # pemisah antar huruf dihapus
    ("Dompet L.V monogram k.w", "dompet lv monogram kw"),
    ("4irsoft AEG M4", "airsoft aeg ma"),                   # efek samping yang diterima: m4 -> ma
    ("Senapan angin kaliber 4.5", "senapan angin kaliber 4.5"),
    ("BB turun 8kg/minggu", "bb turun 8kg/minggu"),
    ("arak-arakan", "arak-arakan"),                          # kata berstrip tidak digabung
])
def test_normalize(raw, expected):
    assert normalize_for_rules(raw) == expected


@pytest.fixture(scope="module")
def engine():
    return RuleEngine.from_file(ROOT / "data/rules/rules.json")


def kinds(engine, title):
    return {(h.term, h.kind) for h in engine.match(make_listing(title=title))}


def test_hard_hit_after_normalization(engine):
    assert ("alpra", "hard") in kinds(engine, "alpr4 1mg buat tidur nyenyak")


def test_word_boundary_prevents_false_match(engine):
    # "judi" tidak boleh cocok di dalam "perjudian", "arak" tidak boleh cocok di "arakan"
    assert kinds(engine, "Buku sejarah perjudian di Nusantara") == set()
    assert not any(k == "hard" for _, k in kinds(engine, "Festival arak-arakan budaya"))


def test_common_words_are_not_hard(engine):
    for title in ("Mainan pistol air untuk anak", "Bir pletok khas Betawi", "Permen coklat bentuk rokok"):
        assert not any(k == "hard" for _, k in kinds(engine, title)), title
