import pytest

from src.path_safety import safe_output_path


@pytest.mark.parametrize(
    'name',
    [
        '../outside.json',
        '..\\outside.json',
        '/tmp/outside.json',
        'C:\\temp\\outside.json',
        'nested/outside.json',
        'nested\\outside.json',
        'bad:name.json',
        'CON',
    ],
)
def test_safe_output_path_rejects_unsafe_names(tmp_path, name):
    with pytest.raises(ValueError):
        safe_output_path(tmp_path, name)


def test_safe_output_path_accepts_plain_file_name(tmp_path):
    assert safe_output_path(tmp_path, 'report.json') == tmp_path / 'report.json'


def test_validated_path_write_stays_inside_output_dir(tmp_path):
    path = safe_output_path(tmp_path, 'safe.txt')
    path.write_text('ok', encoding='utf-8')

    assert path == tmp_path / 'safe.txt'
    assert path.read_text(encoding='utf-8') == 'ok'
