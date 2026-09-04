from types import SimpleNamespace

from app.services.question_bank.release_publish import QuestionBankReleasePublishWorkflowService


class FakeQuery:
    def __init__(self, rows):
        self.rows = list(rows)

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, questions):
        self.questions = questions

    def query(self, model):
        return FakeQuery(self.questions)


class FakeParent:
    def __init__(self, questions):
        self.db = FakeDB(questions)


def q(qid, *, duplicate=False, retired=False, root=None, status='approved'):
    return SimpleNamespace(
        id=qid,
        bank_version_id='v1',
        status=status,
        is_duplicate=duplicate,
        is_retired=retired,
        lineage_root_question_id=root,
        previous_question_id=None,
        difficulty='easy',
        question_family_id=f'family-{qid}',
        created_at=None,
    )


def test_release_selection_auto_excludes_duplicate_retired_and_duplicate_lineage():
    questions = [
        q('good-1', root='root-a'),
        q('same-lineage', root='root-a'),
        q('explicit-duplicate', duplicate=True, root='root-b'),
        q('retired', retired=True, root='root-c'),
        q('good-2', root='root-d'),
    ]
    service = QuestionBankReleasePublishWorkflowService(FakeParent(questions))
    selected, excluded = service._release_question_selection(SimpleNamespace(id='v1'))
    assert [item.id for item in selected] == ['good-1', 'good-2']
    by_id = {item['question_id']: item for item in excluded}
    assert by_id['same-lineage']['reasons'] == ['duplicate_lineage']
    assert by_id['same-lineage']['kept_question_id'] == 'good-1'
    assert by_id['explicit-duplicate']['reasons'] == ['duplicate']
    assert by_id['retired']['reasons'] == ['retired']
