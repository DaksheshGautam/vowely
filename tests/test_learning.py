from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from localflow.config import Config
from localflow.learning import corrected_words, EditSession, LearnedDictionary
from localflow.policy import Target
from localflow.draftwatch import DraftWatch


class LearningTests(unittest.TestCase):
    def test_single_word_spelling_changes_are_learned(self):
        self.assertEqual(corrected_words('Meet Jan today.','Meet Jane today.'),['Jane'])
        self.assertEqual(corrected_words('Acma','Acme'),['Acme'])
        self.assertEqual(corrected_words('Use user_idd here.','Use user_id here.'),['user_id'])
        self.assertEqual(corrected_words('Meet Jose.','Meet Jose\u0301.'),['Jose\u0301'])

    def test_learning_switch_requires_a_boolean(self):
        with self.assertRaises(ValueError): replace(Config(),learn_corrections='true').validate()

    def test_numbers_urls_sentences_and_unrelated_additions_are_ignored(self):
        for before,after in [('Pay 500','Pay 600'),('Hello','Hello. Buy milk.'),
                             ('Meet John','Meet'),('cat','Cat'),('cat.','cat!'),
                             ('a@acma.com','a@acme.com'),('src/acma.py','src/acme.py'),
                             ('id_1234567','id_1234568')]:
            with self.subTest(before=before): self.assertEqual(corrected_words(before,after),[])

    def test_multiple_corrections_and_added_sentences(self):
        self.assertEqual(corrected_words('Meet Jan at Acma with Jon.',
            'Meet Jane at Acme with John. Buy milk too.'),['Jane','Acme','John'])
        self.assertEqual(corrected_words('Meet JohnSmith.','Meet John Smith.'),['John','Smith'])

    def test_no_typing_pause_or_intermediate_spelling_is_learned(self):
        session = EditSession('Meet Jan at Acma.',0)
        self.assertEqual(session.observe('Meet Ja at Acma.',1),[])
        self.assertEqual(session.observe('Meet Jane at Acma.',1.1),[])
        self.assertEqual(session.observe('Meet Jane at Acme. Extra typing.',1.2),[])
        self.assertEqual(session.finish(),['Jane','Acme'])
        self.assertEqual(session.finish(),[])

    def test_clearing_the_box_finalizes_the_latest_draft(self):
        session = EditSession('Meet Jan at Acma.',0)
        session.observe('Meet Jane at Acme.',1)
        self.assertEqual(session.observe('',1.01),['Jane','Acme'])
        self.assertFalse(session.active)

    def test_expiry_discards_draft_without_learning(self):
        session = EditSession('Hello Jan.',0)
        self.assertEqual(session.observe('Hello Jane.',601),[])
        self.assertEqual(session.finish(),[])

    def test_existing_typed_content_is_excluded_from_learning(self):
        before = 'Meet Jan. Call Jon today. Bye Acma.'
        start = before.index('Call')
        end = start+len('Call Jon today.')
        self.assertEqual(corrected_words(before,'Meet Jane. Call John today. Bye Acme.',(start,end)),['John'])

    def test_persistence_contains_only_corrected_spellings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'dictionary.json'
            store = LearnedDictionary(path)
            self.assertEqual(store.add(['Jane','JANE','500','Acme']),['Jane','Acme'])
            self.assertEqual(json.loads(path.read_text()),{'version':1,'words':['Jane','Acme']})
            self.assertEqual(LearnedDictionary(path).words,['Jane','Acme'])
            store.remove(['Jane'])
            self.assertEqual(LearnedDictionary(path).words,['Acme'])

    def test_manual_vocabulary_keeps_priority_and_prompt_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LearnedDictionary(Path(tmp)/'dictionary.json')
            store.add(['Term'+str(i) for i in range(140)])
            self.assertEqual(len(store.words),128)
            vocab = store.vocabulary(['ManualName'])
            self.assertEqual(vocab[0],'ManualName')
            self.assertEqual(len(vocab),32)
            self.assertIn('Term139',vocab)

    def test_corrupt_dictionary_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'dictionary.json'
            path.write_text('broken data')
            store = LearnedDictionary(path)
            self.assertFalse(store.available)
            with self.assertRaises(OSError): store.add(['Jane'])
            self.assertEqual(path.read_text(),'broken data')

    def test_start_in_password_or_changed_target_never_reads_text(self):
        target = Target(1,2,'editor.exe',(1,2),'','Editor',False,True)
        for current in (replace(target,password=True),replace(target,runtime_id=(1,3)),
                        replace(target,name='Password'),replace(target,editable=False),None):
            native = Mock()
            native._snapshot_direct.return_value = current
            watch = DraftWatch(native,target,Config(),'Meet Jan.')
            self.assertFalse(watch.start())
            native.uia.GetFocusedElement.assert_not_called()

    def test_leaving_field_finishes_cache_without_reading_new_field(self):
        watch = DraftWatch(Mock(),Mock(),Config(),'Meet Jan.')
        watch.session = EditSession('Meet Jan.',0)
        watch.session.observe('Meet Jane.',1)
        watch.session.deadline = float('inf')
        watch.eligible = lambda:True
        watch.focused = lambda:False
        watch.capture = Mock()
        self.assertEqual(watch.poll(),{'status':'finished','words':['Jane']})
        watch.capture.assert_not_called()

    def test_repurposed_sensitive_field_discards_pending_corrections(self):
        watch = DraftWatch(Mock(),Mock(),Config(),'Meet Jan.')
        watch.session = EditSession('Meet Jan.',0)
        watch.session.observe('Meet Jane.',1)
        watch.eligible = lambda:False
        self.assertEqual(watch.poll(),{'status':'finished','words':[]})

    def test_completed_words_survive_composer_removal_without_querying_it(self):
        watch = DraftWatch(Mock(),Mock(),Config(),'Meet Jan.')
        watch.session = EditSession('Meet Jan.',0)
        watch.completed = ['Jane']
        watch.eligible = Mock(side_effect=RuntimeError('Composer removed after send'))
        self.assertEqual(watch.poll(),{'status':'finished','words':['Jane']})
        watch.eligible.assert_not_called()

    def test_numeric_edit_does_not_discard_other_corrected_words(self):
        self.assertEqual(corrected_words('Meet Jan at 500, call Jon.',
                                        'Meet Jane at 600, call John.'),['Jane','John'])


if __name__=='__main__': unittest.main()
