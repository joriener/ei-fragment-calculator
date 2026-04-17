"""Quick sanity check for sdf_writer ChemVista compatibility fixes."""
from ei_fragment_calculator.sdf_writer import write_exact_masses_sdf
from pathlib import Path

# Minimal test record: no NAME field, no M  END, no NUM PEAKS
results = [{
    'record_index': 0,
    'compound_name': 'Vanillin',
    'mol_block': 'Vanillin\n  TEST\n\n  0  0\n',
    'fields': {
        'MOLECULAR FORMULA': 'C8H8O3',
        'MW': '152',
        'MASS SPECTRAL PEAKS': '151 999\n152 929',
    },
    'peak_mz': 151,
    'candidate': {
        'ion_mass': 151.039000,
        'delta_mass': 0.0,
        'filter_passed': True,
        'isotope_score': 0.1,
    },
}]

out = 'D:/Test/test-writer-check.sdf'
write_exact_masses_sdf(results, out)
txt = Path(out).read_text(encoding='utf-8')
print(txt)
print('--- CHECKS ---')
print('NAME field:    ', '> <NAME>' in txt)
print('FORMULA field: ', '> <FORMULA>' in txt)
print('NUM PEAKS:     ', '> <NUM PEAKS>' in txt)
print('M  END:        ', 'M  END' in txt)
assert '> <NAME>' in txt,         "MISSING: <NAME>"
assert '> <FORMULA>' in txt,      "MISSING: <FORMULA>"
assert '> <NUM PEAKS>' in txt,    "MISSING: <NUM PEAKS>"
assert 'M  END' in txt,           "MISSING: M  END"
print('ALL CHECKS PASSED')
