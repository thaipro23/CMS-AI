from app.modules.publisher.service import OpenEdXPublisher


def test_real_problem_bank_guard_accepts_only_verified_native_itembank():
    result = {
        'ok': True,
        'implementation': 'native_ulmo_itembank',
        'problem_bank_blocks': [
            {
                'usage_key': 'block-v1:FPT+DOM123+SU26+type@itembank+block@slot-01',
                'block_type': 'itembank',
                'selection_verified': True,
            }
        ],
    }
    assert OpenEdXPublisher._looks_like_real_problem_bank_insert(result) is True


def test_real_problem_bank_guard_rejects_legacy_randomized_content_and_unverified_bank():
    legacy = {
        'ok': True,
        'implementation': 'native_ulmo_itembank',
        'problem_bank_blocks': [
            {
                'usage_key': 'block-v1:FPT+DOM123+SU26+type@library_content+block@slot-01',
                'block_type': 'library_content',
                'selection_verified': True,
            }
        ],
    }
    unverified = {
        'ok': True,
        'implementation': 'native_ulmo_itembank',
        'problem_bank_blocks': [
            {
                'usage_key': 'block-v1:FPT+DOM123+SU26+type@itembank+block@slot-01',
                'block_type': 'itembank',
                'selection_verified': False,
            }
        ],
    }
    assert OpenEdXPublisher._looks_like_real_problem_bank_insert(legacy) is False
    assert OpenEdXPublisher._looks_like_real_problem_bank_insert(unverified) is False
