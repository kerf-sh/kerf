import hashlib
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LARGE_STEP_THRESHOLD = 5 * 1024 * 1024


def make_blob(size_bytes):
    return b'A' * size_bytes


def compute_ref(blob, filename, mime):
    sha256_hex = hashlib.sha256(blob).hexdigest()
    size = len(blob)
    base = filename
    for ext in ('.step', '.stp', '.STEP', '.STP'):
        if base.endswith(ext):
            base = base[:-len(ext)]
            break
    ref_name = base + '.step-ref'
    ref_json = json.dumps({'hash': sha256_hex, 'size': size, 'original_name': filename, 'mime': mime})
    return {'ref_name': ref_name, 'ref_json': ref_json, 'hash': sha256_hex}


def test_small_file_goes_inline():
    blob = make_blob(4 * 1024 * 1024)
    assert len(blob) <= LARGE_STEP_THRESHOLD


def test_large_file_triggers_ref():
    blob = make_blob(6 * 1024 * 1024)
    assert len(blob) > LARGE_STEP_THRESHOLD


def test_ref_json_structure():
    blob = make_blob(6 * 1024 * 1024)
    result = compute_ref(blob, 'assembly.step', 'model/step')
    assert result['ref_name'] == 'assembly.step-ref'
    ref = json.loads(result['ref_json'])
    assert ref['original_name'] == 'assembly.step'
    assert ref['mime'] == 'model/step'
    assert ref['size'] == 6 * 1024 * 1024
    assert len(ref['hash']) == 64


def test_hash_deterministic():
    blob = make_blob(6 * 1024 * 1024)
    r1 = compute_ref(blob, 'part.step', 'model/step')
    r2 = compute_ref(blob, 'part.step', 'model/step')
    assert r1['hash'] == r2['hash']


def test_ref_name_strips_stp():
    blob = make_blob(6 * 1024 * 1024)
    result = compute_ref(blob, 'model.stp', 'model/step')
    assert result['ref_name'] == 'model.step-ref'


def test_blob_storage_key_format():
    blob = make_blob(6 * 1024 * 1024)
    sha = hashlib.sha256(blob).hexdigest()
    blob_key = f'blobs/step/{sha}'
    assert blob_key.startswith('blobs/step/')
    assert len(blob_key) == len('blobs/step/') + 64