import importlib.util
from pathlib import Path

import pytest

from vertia.chat.rgpd import anonymize_details, anonymize_text


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('benchmark_rgpd', ROOT / 'scripts/benchmark_rgpd.py')
# Les dataclasses du benchmark résolvent leurs annotations dans sys.modules.
import sys
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)
CORPUS = benchmark.load_corpus(benchmark.DEFAULT_CORPUS)


@pytest.mark.parametrize('case', [c for c in CORPUS['cases'] if c['id'] in CORPUS['required_exact_cases']], ids=lambda c: c['id'])
def test_required_exact(case):
    expected = benchmark.build_expected_output(case['input'], case['expected_sensitive'])
    assert anonymize_text(case['input']) == (expected, len(case['expected_sensitive']))


def test_benchmark_gate():
    result = benchmark.run_benchmark(CORPUS)
    assert result.total_cases == 26
    assert len(result.required_exact_cases) == 21
    assert result.thresholds_met


@pytest.mark.parametrize('value', ['FR7630006000011234567890188', '1234 5678 9012 3456', '999.999.999.999'])
def test_invalid_validated_data_is_unchanged(value):
    assert anonymize_text(value) == (value, 0)


def test_counts_and_determinism():
    text = 'Mme Alice Martin : alice@example.fr, 06 12 34 56 78'
    first = anonymize_details(text)
    assert first == anonymize_details(text)
    assert first[1] == {'email': 1, 'telephone': 1, 'nom': 1}
