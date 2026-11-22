"""Unit tests for the image testfunction collection (PNG text chunks, EXIF, dimensions)."""

import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image, TiffImagePlugin

from adarelib.constants import StatusEnum
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
image = import_module_from_pyfile(COLLECTIONS / 'image' / 'image.py')

PngTextMatches = image.png_text_matches._test_class
PngTextCount = image.png_text_count._test_class
ExifValueMatches = image.exif_value_matches._test_class
ExifValueCount = image.exif_value_count._test_class
DimensionsMatch = image.dimensions_match._test_class

_PARAMS = {
    PngTextMatches: image.png_text_matches._parameter_class,
    PngTextCount: image.png_text_count._parameter_class,
    ExifValueMatches: image.exif_value_matches._parameter_class,
    ExifValueCount: image.exif_value_count._parameter_class,
    DimensionsMatch: image.dimensions_match._parameter_class,
}


def _run(test_class, **params):
    return test_class(name='t', parameter=_PARAMS[test_class](**params)).test()


def _assert(result, status):
    assert result.status == status, f'{result.status}: {result.details}'


# --- PNG builders (stdlib only) ---------------------------------------------------------


def _chunk(ctype: bytes, body: bytes, crc: int | None = None) -> bytes:
    if crc is None:
        crc = zlib.crc32(ctype + body) & 0xFFFFFFFF
    return struct.pack('>I', len(body)) + ctype + body + struct.pack('>I', crc)


def _ihdr(width=3, height=2) -> bytes:
    return _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))


def _idat(width=3, height=2) -> bytes:
    rows = b''.join(b'\x00' + b'\x80' * width for _ in range(height))
    return _chunk(b'IDAT', zlib.compress(rows))


def _text(keyword: str, text: str) -> bytes:
    return _chunk(b'tEXt', keyword.encode('latin-1') + b'\x00' + text.encode('latin-1'))


def _ztxt(keyword: str, text: str) -> bytes:
    return _chunk(b'zTXt', keyword.encode('latin-1') + b'\x00\x00' + zlib.compress(text.encode('latin-1')))


def _itxt(keyword: str, text: str, compressed=False, lang='de', translated='Kommentar') -> bytes:
    data = text.encode('utf-8')
    if compressed:
        data = zlib.compress(data)
    head = keyword.encode('latin-1') + b'\x00' + bytes([1 if compressed else 0, 0])
    return _chunk(b'iTXt', head + lang.encode() + b'\x00' + translated.encode('utf-8') + b'\x00' + data)


def _png(*chunks: bytes, after_idat: tuple[bytes, ...] = (), iend=True) -> bytes:
    data = image.PNG_SIGNATURE + _ihdr() + b''.join(chunks) + _idat() + b''.join(after_idat)
    return data + (_chunk(b'IEND', b'') if iend else b'')


@pytest.fixture
def png(tmp_path):
    path = tmp_path / 'photo.png'
    path.write_bytes(
        _png(
            _text('Comment', 'first'),
            _ztxt('Source', 'scanner 42'),
            _itxt('Title', 'Grüße aus Bonn', compressed=True),
            _itxt('Comment', 'zweiter Kommentar'),
            after_idat=(_text('Late', 'after the image data'),),
        )
    )
    return str(path)


def _write(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


# --- PNG parser -------------------------------------------------------------------------


def test_parser_reads_all_text_chunks(png):
    texts = image.parse_png_text(Path(png).read_bytes())
    assert [(t.chunk, t.keyword, t.text) for t in texts] == [
        ('tEXt', 'Comment', 'first'),
        ('zTXt', 'Source', 'scanner 42'),
        ('iTXt', 'Title', 'Grüße aus Bonn'),
        ('iTXt', 'Comment', 'zweiter Kommentar'),
        ('tEXt', 'Late', 'after the image data'),
    ]


def test_pillow_can_open_the_hand_built_png(png):
    with Image.open(png) as img:
        assert img.size == (3, 2)


@pytest.mark.parametrize(
    ('data', 'message'),
    [
        (b'GIF89a not a png', 'bad signature'),
        (_png(_chunk(b'tEXt', b'Comment\x00x', crc=1)), 'CRC mismatch'),
        (_png(after_idat=(_chunk(b'tEXt', b'Late\x00x', crc=1),)), 'CRC mismatch'),
        (_png(_text('Comment', 'x'))[:-6], 'truncated'),
        (_png(_text('Comment', 'x'), iend=False), 'no IEND'),
        (_png(_chunk(b'tEXt', b'no terminator')), 'no keyword terminator'),
        (_png(_chunk(b'zTXt', b'k\x00\x00not zlib')), 'cannot decompress'),
        (_png(_chunk(b'zTXt', b'k\x00\x01' + zlib.compress(b'x'))), 'compression method'),
        (_png(_chunk(b'zTXt', b'k\x00\x00' + zlib.compress(b'some longer text' * 20)[:-8])), 'truncated'),
        (_png(_chunk(b'iTXt', b'k\x00\x00\x00de')), 'terminator'),
        (_png(_chunk(b'iTXt', b'k\x00\x00\x00\x00\x00\xff\xfe')), 'not UTF-8'),
    ],
    ids=[
        'signature',
        'crc',
        'crc-after-idat',
        'truncated',
        'no-iend',
        'text',
        'ztxt',
        'method',
        'ztxt-cut',
        'itxt',
        'utf8',
    ],
)
def test_parser_rejects_corrupt_png(data, message):
    with pytest.raises(image.PngError, match=message):
        image.parse_png_text(data)


def test_parser_refuses_decompression_bomb(monkeypatch):
    monkeypatch.setattr(image, 'MAX_TEXT_BYTES', 10)
    with pytest.raises(image.PngError, match='exceeds'):
        image.parse_png_text(_png(_ztxt('k', 'x' * 100)))


# --- png_text_matches -------------------------------------------------------------------


def test_png_text_key_exists(png):
    _assert(_run(PngTextMatches, dst=png, keyword='Source'), StatusEnum.SUCCESS)
    _assert(_run(PngTextMatches, dst=png, keyword='Late'), StatusEnum.SUCCESS)  # after IDAT


def test_png_text_key_missing_fails(png):
    result = _run(PngTextMatches, dst=png, keyword='Software')
    _assert(result, StatusEnum.FAILED)
    assert 'Comment' in result.details[1]


def test_png_text_key_is_case_sensitive(png):
    _assert(_run(PngTextMatches, dst=png, keyword='comment'), StatusEnum.FAILED)


def test_png_text_value(png):
    _assert(_run(PngTextMatches, dst=png, keyword='Source', expected_value='scanner 42'), StatusEnum.SUCCESS)
    _assert(_run(PngTextMatches, dst=png, keyword='Title', expected_value='Grüße aus Bonn'), StatusEnum.SUCCESS)
    _assert(_run(PngTextMatches, dst=png, keyword='Source', expected_value='scanner 7'), StatusEnum.FAILED)


def test_png_text_duplicates_any_match(png):
    _assert(_run(PngTextMatches, dst=png, keyword='Comment', expected_value='zweiter Kommentar'), StatusEnum.SUCCESS)
    result = _run(PngTextMatches, dst=png, keyword='Comment', expected_value='third')
    _assert(result, StatusEnum.FAILED)
    assert '0/2' in result.details[0]


def test_png_text_regex(png):
    _assert(
        _run(PngTextMatches, dst=png, keyword='Source', expected_value=r'\d+$', regex_match=True), StatusEnum.SUCCESS
    )
    _assert(_run(PngTextMatches, dst=png, keyword='Source', expected_value='[', regex_match=True), StatusEnum.ERROR)


def test_png_text_number_compares_as_text(tmp_path):
    path = _write(tmp_path, 'n.png', _png(_text('Version', '3')))
    _assert(_run(PngTextMatches, dst=path, keyword='Version', expected_value=3), StatusEnum.SUCCESS)


# --- png_text_count ---------------------------------------------------------------------


def test_png_text_count(png):
    _assert(_run(PngTextCount, dst=png, keyword='Comment', expected_count=2), StatusEnum.SUCCESS)
    _assert(_run(PngTextCount, dst=png, keyword='Comment', expected_count=1), StatusEnum.FAILED)
    _assert(
        _run(PngTextCount, dst=png, keyword='Comment', expected_count=1, expected_value='first'), StatusEnum.SUCCESS
    )
    _assert(
        _run(PngTextCount, dst=png, keyword='Comment', expected_count=1, comparison_type='greater'), StatusEnum.SUCCESS
    )


def test_png_text_count_zero_asserts_absence(png):
    _assert(_run(PngTextCount, dst=png, keyword='Software', expected_count=0), StatusEnum.SUCCESS)
    _assert(_run(PngTextCount, dst=png, keyword='Late', expected_count=0), StatusEnum.FAILED)


@pytest.mark.parametrize(
    'params',
    [
        {'expected_count': -1},
        {'expected_count': 1.5},
        {'expected_count': 1, 'comparison_type': 'nope'},
        {'expected_count': 1, 'expected_value': '(', 'regex_match': True},
    ],
)
def test_png_text_count_bad_parameters_are_errors(png, params):
    _assert(_run(PngTextCount, dst=png, keyword='Comment', **params), StatusEnum.ERROR)


@pytest.mark.parametrize('test_class', [PngTextMatches, PngTextCount])
def test_png_bad_crc_is_error(tmp_path, test_class):
    path = _write(tmp_path, 'bad.png', _png(_chunk(b'tEXt', b'Comment\x00x', crc=0)))
    params = {'expected_count': 1} if test_class is PngTextCount else {}
    result = _run(test_class, dst=path, keyword='Comment', **params)
    _assert(result, StatusEnum.ERROR)
    assert 'CRC mismatch' in result.details[0]


@pytest.mark.parametrize('test_class', [PngTextMatches, PngTextCount])
def test_png_not_a_png_is_error(tmp_path, test_class):
    path = _write(tmp_path, 'fake.png', b'just text')
    params = {'expected_count': 0} if test_class is PngTextCount else {}
    _assert(_run(test_class, dst=path, keyword='Comment', **params), StatusEnum.ERROR)


# --- EXIF -------------------------------------------------------------------------------


def _jpeg_with_exif(path: Path) -> str:
    exif = Image.Exif()
    exif[0x010F] = 'ACME'  # Make
    exif[0x0110] = 'Model X'  # Model
    exif[0x011A] = TiffImagePlugin.IFDRational(72, 1)  # XResolution
    exif[0x0131] = 'Editor 1.0'  # Software
    exif[0x9C9B] = 'Urlaub'.encode('utf-16-le') + b'\x00\x00'  # UTF-16 title tag
    exif_ifd = exif.get_ifd(image.EXIF_IFD)
    exif_ifd[0x9003] = '2024:05:01 12:00:00'  # DateTimeOriginal
    exif_ifd[0x829D] = TiffImagePlugin.IFDRational(28, 10)  # FNumber
    exif_ifd[0x829A] = TiffImagePlugin.IFDRational(1, 250)  # ExposureTime
    exif_ifd[0x8827] = 200  # ISOSpeedRatings
    exif_ifd[0x9286] = b'ASCII\x00\x00\x00holiday'  # UserComment
    exif_ifd[0x9000] = b'0232'  # ExifVersion
    gps = exif.get_ifd(image.GPS_IFD)
    gps[1] = 'N'  # GPSLatitudeRef
    gps[2] = (
        TiffImagePlugin.IFDRational(51, 1),
        TiffImagePlugin.IFDRational(30, 1),
        TiffImagePlugin.IFDRational(125, 10),
    )
    Image.new('RGB', (40, 30), 'red').save(path, 'JPEG', exif=exif)
    return str(path)


@pytest.fixture
def jpeg(tmp_path):
    return _jpeg_with_exif(tmp_path / 'photo.jpg')


@pytest.fixture
def plain_jpeg(tmp_path):
    path = tmp_path / 'plain.jpg'
    Image.new('RGB', (10, 10)).save(path, 'JPEG')
    return str(path)


@pytest.mark.parametrize(
    ('tag', 'expected'),
    [
        ('Make', 'ACME'),
        ('Model', 'Model X'),
        ('0x010f', 'ACME'),
        (271, 'ACME'),
        ('271', 'ACME'),
        ('XResolution', '72'),
        ('XResolution', 72),
        ('DateTimeOriginal', '2024:05:01 12:00:00'),
        ('FNumber', '2.8'),
        ('FNumber', 2.8),
        ('ExposureTime', '0.004'),
        ('ISOSpeedRatings', 200),
        ('UserComment', 'holiday'),
        ('ExifVersion', '0232'),
        ('XPTitle', 'Urlaub'),
        ('GPSLatitudeRef', 'N'),
        ('GPSLatitude', '51, 30, 12.5'),
        ('GPSLatitude', [51, 30, 12.5]),
    ],
)
def test_exif_value_matches(jpeg, tag, expected):
    _assert(_run(ExifValueMatches, dst=jpeg, tag=tag, expected_value=expected), StatusEnum.SUCCESS)


def test_exif_value_mismatch_fails(jpeg):
    result = _run(ExifValueMatches, dst=jpeg, tag='Make', expected_value='Other')
    _assert(result, StatusEnum.FAILED)
    assert 'IFD0' in result.details[0]


def test_exif_missing_tag_fails(jpeg, plain_jpeg):
    _assert(_run(ExifValueMatches, dst=jpeg, tag='Artist', expected_value='x'), StatusEnum.FAILED)
    _assert(_run(ExifValueMatches, dst=plain_jpeg, tag='Make', expected_value='ACME'), StatusEnum.FAILED)


def test_exif_regex(jpeg):
    _assert(
        _run(ExifValueMatches, dst=jpeg, tag='DateTimeOriginal', expected_value='^2024:05', regex_match=True),
        StatusEnum.SUCCESS,
    )
    _assert(_run(ExifValueMatches, dst=jpeg, tag='Make', expected_value='(', regex_match=True), StatusEnum.ERROR)


@pytest.mark.parametrize('tag', ['NoSuchTag', '0xZZ', 0x10000, -1, True, 1.5])
def test_exif_bad_tag_is_error(jpeg, tag):
    _assert(_run(ExifValueMatches, dst=jpeg, tag=tag, expected_value='x'), StatusEnum.ERROR)
    _assert(_run(ExifValueCount, dst=jpeg, tag=tag, expected_count=0), StatusEnum.ERROR)


def test_exif_count(jpeg):
    _assert(_run(ExifValueCount, dst=jpeg, tag='Make', expected_count=1), StatusEnum.SUCCESS)
    _assert(_run(ExifValueCount, dst=jpeg, tag='Make', expected_count=2), StatusEnum.FAILED)
    _assert(_run(ExifValueCount, dst=jpeg, tag='Make', expected_count=1, expected_value='ACME'), StatusEnum.SUCCESS)
    _assert(_run(ExifValueCount, dst=jpeg, tag='Make', expected_count=0, expected_value='Other'), StatusEnum.SUCCESS)


def test_exif_count_zero_asserts_absence(jpeg, plain_jpeg):
    _assert(_run(ExifValueCount, dst=plain_jpeg, tag='GPSLatitude', expected_count=0), StatusEnum.SUCCESS)
    _assert(_run(ExifValueCount, dst=jpeg, tag='GPSLatitude', expected_count=0), StatusEnum.FAILED)


def test_exif_numeric_tag_searches_every_ifd(jpeg):
    # 2 is GPSLatitude in the GPS IFD; IFD0 and the Exif IFD have no tag 2
    _assert(_run(ExifValueCount, dst=jpeg, tag=2, expected_count=1), StatusEnum.SUCCESS)


@pytest.mark.parametrize(
    'params',
    [{'expected_count': -1}, {'expected_count': 1, 'comparison_type': 'x'}],
)
def test_exif_count_bad_parameters_are_errors(jpeg, params):
    _assert(_run(ExifValueCount, dst=jpeg, tag='Make', **params), StatusEnum.ERROR)


@pytest.mark.parametrize('test_class', [ExifValueMatches, ExifValueCount, DimensionsMatch])
@pytest.mark.parametrize('data', [b'not an image at all', b'\xff\xd8\xff\xe0 truncated jpeg'], ids=['text', 'jpeg'])
def test_not_an_image_is_error(tmp_path, test_class, data):
    path = _write(tmp_path, 'bad.jpg', data)
    params = {
        ExifValueMatches: {'tag': 'Make', 'expected_value': 'x'},
        ExifValueCount: {'tag': 'Make', 'expected_count': 0},
        DimensionsMatch: {'width': 1},
    }[test_class]
    _assert(_run(test_class, dst=path, **params), StatusEnum.ERROR)


def test_png_exif_chunk(tmp_path):
    exif = Image.Exif()
    exif[0x010F] = 'ACME'
    path = tmp_path / 'exif.png'
    Image.new('RGB', (4, 4)).save(path, 'PNG', exif=exif)
    _assert(_run(ExifValueMatches, dst=str(path), tag='Make', expected_value='ACME'), StatusEnum.SUCCESS)


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (TiffImagePlugin.IFDRational(1, 0), 'nan'),
        (b'\x01\x02\xff', '0102ff'),
        (b'abc\x00\x00', 'abc'),
        (b'UNICODE\x00' + 'hi'.encode('utf-16'), 'hi'),
        ('text\x00', 'text'),
        ((1, 2, 3), '1, 2, 3'),
        (3.0, '3'),
    ],
)
def test_format_exif_value(value, expected):
    tag_id = image.USER_COMMENT if isinstance(value, bytes) and value.startswith(b'UNICODE') else -1
    assert image.format_exif_value(value, tag_id) == expected


# --- dimensions_match -------------------------------------------------------------------


def test_dimensions(jpeg, png):
    _assert(_run(DimensionsMatch, dst=jpeg, width=40, height=30), StatusEnum.SUCCESS)
    _assert(_run(DimensionsMatch, dst=jpeg, width=40), StatusEnum.SUCCESS)
    _assert(_run(DimensionsMatch, dst=png, height=2), StatusEnum.SUCCESS)


def test_dimensions_mismatch_fails(jpeg):
    result = _run(DimensionsMatch, dst=jpeg, width=40, height=31)
    _assert(result, StatusEnum.FAILED)
    assert 'height 30 != expected 31' in result.details


@pytest.mark.parametrize('params', [{}, {'width': 0}, {'height': -3}, {'width': '40'}, {'width': True}], ids=str)
def test_dimensions_bad_parameters_are_errors(jpeg, params):
    _assert(_run(DimensionsMatch, dst=jpeg, **params), StatusEnum.ERROR)


# --- missing file / globs (every function) ----------------------------------------------

ALL = [
    (PngTextMatches, {'keyword': 'k'}),
    (PngTextCount, {'keyword': 'k', 'expected_count': 0}),
    (ExifValueMatches, {'tag': 'Make', 'expected_value': 'x'}),
    (ExifValueCount, {'tag': 'Make', 'expected_count': 0}),
    (DimensionsMatch, {'width': 1}),
]
IDS = ['png_text_matches', 'png_text_count', 'exif_value_matches', 'exif_value_count', 'dimensions_match']


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_missing_file_is_error(tmp_path, test_class, params):
    result = _run(test_class, dst=str(tmp_path / 'missing.png'), **params)
    _assert(result, StatusEnum.ERROR)
    assert 'does not exist' in result.details[0]


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_glob_without_match_is_error(tmp_path, test_class, params):
    _assert(_run(test_class, dst=str(tmp_path / 'none*.png'), **params), StatusEnum.ERROR)


@pytest.mark.parametrize(('test_class', 'params'), ALL, ids=IDS)
def test_ambiguous_glob_is_error(tmp_path, test_class, params):
    _write(tmp_path, 'a1.png', _png())
    _write(tmp_path, 'a2.png', _png())
    _assert(_run(test_class, dst=str(tmp_path / 'a*.png'), **params), StatusEnum.ERROR)


def test_glob_with_one_match(tmp_path):
    _write(tmp_path, 'only.png', _png(_text('k', 'v')))
    _assert(_run(PngTextMatches, dst=str(tmp_path / 'on*.png'), keyword='k', expected_value='v'), StatusEnum.SUCCESS)


def _corrupt_exif(path: Path, how: str) -> str:
    """A JPEG whose EXIF TIFF header is broken: bad magic, or IFD0 offset past the segment."""
    data = Path(_jpeg_with_exif(path)).read_bytes()
    tiff = data.find(b'Exif\x00\x00') + 6
    if how == 'magic':
        data = data[:tiff] + b'XX' + data[tiff + 2 :]
    else:
        order = 'little' if data[tiff : tiff + 2] == b'II' else 'big'
        data = data[: tiff + 4] + (0xFFFF).to_bytes(4, order) + data[tiff + 8 :]
    path.write_bytes(data)
    return str(path)


@pytest.mark.parametrize('how', ['magic', 'offset'])
def test_corrupt_exif_is_an_error_not_absence(tmp_path, how):
    path = _corrupt_exif(tmp_path / 'bad_exif.jpg', how)
    result = _run(image.exif_value_count._test_class, dst=path, tag='Make', expected_count=0)
    _assert(result, StatusEnum.ERROR)
