from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from localflow.config import Config
from localflow.learning import corrected_words, EditSession, LearnedDictionary
from localflow.policy import Target
from localflow.windows import Windows


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
                             ('Meet Jan now','See Jane now'),('id_1234567','id_1234568')]:
            with self.subTest(before=before): self.assertEqual(corrected_words(before,after),[])

    def test_edit_must_settle_before_learning_and_is_not_repeated(self):
        session = EditSession('Meet Jan today.',0)
        self.assertEqual(session.observe('Meet Jane today.',1),[])
        self.assertEqual(session.observe('Meet Jane today.',2),[])
        self.assertEqual(session.observe('Meet Jane today.',3.1),['Jane'])
        self.assertEqual(session.observe('Meet Jane today.',4),[])
        self.assertEqual(session.observe('Meet Jane tomorrow.',5),[])
        self.assertEqual(session.observe('Meet Jane tomorrow.',7.1),['tomorrow'])

    def test_partial_edit_does_not_get_saved_if_typing_continues(self):
        session = EditSession('Meet Jan today.',0)
        session.observe('Meet Ja today.',1)
        session.observe('Meet Jane today.',1.5)
        self.assertEqual(session.observe('Meet Jane today.',3),[])
        self.assertEqual(session.observe('Meet Jane today.',3.6),['Jane'])

    def test_expiry_and_appended_text_end_the_learning_session(self):
        session = EditSession('Hello Jan.',0)
        self.assertEqual(session.observe('Hello Jane.',61),[])
        self.assertFalse(session.active)
        session = EditSession('Hello Jan.',0)
        session.observe('Hello Jan. Other typing.',1)
        session.observe('Hello Jan. Other typing.',4)
        self.assertFalse(session.active)

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

    def test_reading_password_or_changed_target_never_reads_text(self):
        target = Target(1,2,'editor.exe',(1,2),'','Editor',False,True)
        for current in (replace(target,password=True),replace(target,runtime_id=(1,3)),
                        replace(target,name='Password'),replace(target,editable=False),None):
            native = object.__new__(Windows)
            native._snapshot_direct = lambda current=current:current
            span = native._correction_range = Mock()
            self.assertIsNone(native._correction_span_direct(target,Config()))
            span.GetText.assert_not_called()

    def test_caret_outside_the_inserted_range_stops_learning_before_reading(self):
        target = Target(1,2,'editor.exe',(1,2),'','Editor',False,True)
        native = object.__new__(Windows)
        native._snapshot_direct = lambda:target
        native._correction_range = Mock()
        span = native._correction_range
        native._correction_pattern = Mock()
        native._correction_pattern.GetSelection.return_value.Length = 1
        native._correction_pattern.GetSelection.return_value.GetElement.return_value.CompareEndpoints.return_value = -1
        self.assertIsNone(native._correction_span_direct(target,Config()))
        span.GetText.assert_not_called()


if __name__=='__main__': unittest.main()
