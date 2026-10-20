"""Behavioral cases: ordinary prose versus actions, outputs and explicit lists."""
import json
from pathlib import Path
import re
import threading
from types import SimpleNamespace
import unittest

from localflow.config import Config
from localflow.engines import EngineError,validate_cleanup,cleanup_insertion_ready
from localflow.formatting import preserved_cleanup,PreservedCleanupNotice,numbers_preserved,finish_natural_text
from localflow.natural_layout import prepare_layout,layout_retained
from localflow.resident import ResidentModels

CASES=json.loads((Path(__file__).parent/'fixtures/dictation_style.json').read_text(encoding='utf-8'))


class DictationStyleTests(unittest.TestCase):
    def test_unavailable_model_keeps_contextual_layout_and_all_content(self):
        for case in CASES:
            with self.subTest(case=case['id']):
                text,warning=preserved_cleanup(case['raw'],'Model unavailable.')
                self.assertIsInstance(warning,PreservedCleanupNotice)
                self.assertEqual(len(re.findall(r'(?m)^- ',text)),case['bullets'])
                self.assertEqual(len(re.findall(r'(?m)^\d+\. ',text)),case['numbered'])
                for phrase in case['must_keep']:self.assertIn(phrase.casefold(),text.casefold())
                self.assertNotIn('New paragraph',text)
                self.assertNotIn('End list',text)
                self.assertTrue(cleanup_insertion_ready(case['raw'],text,warning,Config(cleanup_enabled=True)))

    def test_grammar_edits_inside_items_are_accepted_but_item_loss_is_not(self):
        raw='The first one is a document with the SQL queries. The second one is a report with the findings. Users download both separately.'
        prepared,anchors=prepare_layout(raw)
        edited='1. A document with SQL queries.\n2. A report with findings.\n\nUsers download both separately.'
        self.assertTrue(layout_retained(prepared,edited,anchors))
        self.assertEqual(validate_cleanup(raw,edited),edited)
        self.assertFalse(layout_retained(prepared,edited.replace('2. A report with findings.\n',''),anchors))
        self.assertFalse(layout_retained(prepared,edited.replace('Users download both separately.',''),anchors))

    def test_resident_accepts_grammar_edits_instead_of_forcing_source_fallback(self):
        raw='The first one is a document with the SQL queries. The second one is a report with the findings. Users download both separately.'
        edited='1. A document with SQL queries.\n2. A report with findings.\n\nUsers download both separately.'
        config=Config(cleanup_enabled=True)
        runtime=ResidentModels(config,Path('.'));self.addCleanup(runtime.close)
        runtime.qwen=SimpleNamespace(request=lambda *args:{'content':edited},close=lambda:None)
        text,warning=runtime.clean(raw,config,threading.Event())
        self.assertEqual(text,edited)
        self.assertNotIsInstance(warning,PreservedCleanupNotice)

    def test_negation_literals_numbers_and_technical_terms_are_protected(self):
        pairs=[('Do not delete original files.','Delete original files.'),
               ('Never upload recordings.','Upload recordings.'),
               ('Use Python, Whisper and Qwen locally.','Use Python locally.'),
               ('Set `save_history = False` as the default.','Set `save_history = True` as the default.'),
               ('The budget is ₹15,000, not ₹50,000.','The budget is ₹50,000, not ₹15,000.')]
        for raw,bad in pairs:
            with self.subTest(raw=raw),self.assertRaises(EngineError):validate_cleanup(raw,bad)

    def test_filler_removal_is_not_confused_with_summarizing(self):
        raw='Um the report is finished the report is finished and I will send it tomorrow.'
        good='The report is finished, and I will send it tomorrow.'
        self.assertEqual(validate_cleanup(raw,good),good)
        raw=CASES[-1]['raw']
        with self.assertRaises(EngineError):validate_cleanup(raw,'An analysis app is ready for testing next week. Please send some files.')

    def test_exact_phrase_restarts_are_removed_but_literals_and_distinct_items_remain(self):
        self.assertEqual(finish_natural_text('The report is finished. The report is finished and I will send it tomorrow.'),
                         'The report is finished and I will send it tomorrow.')
        for text in ('Say "the report is finished the report is finished" exactly.',
                     'Use `print(a, b, c) print(a, b, c)`.',
                     '1. Check the report.\n2. Check the report.',
                     'Code: one two three one two three.',
                     'We need 12 licenses we need 12 licenses.',
                     'Repeat the words red green blue red green blue.'):
            with self.subTest(text=text):self.assertEqual(finish_natural_text(text),text)

    def test_resident_removes_a_restart_that_the_model_leaves_in(self):
        raw='The report is finished the report is finished and I will send it tomorrow.'
        config=Config(cleanup_enabled=True)
        runtime=ResidentModels(config,Path('.'));self.addCleanup(runtime.close)
        runtime.qwen=SimpleNamespace(request=lambda *args:{'content':raw},close=lambda:None)
        text,warning=runtime.clean(raw,config,threading.Event())
        self.assertEqual(text.count('report is finished'),1)
        self.assertTrue(cleanup_insertion_ready(raw,text,warning,config))

    def test_same_verb_correction_resolves_only_an_explicit_nonnegative_restart(self):
        raw='We should cancel the project, no, I mean cancel the old subscription, not the project.'
        expected='We should cancel the old subscription, not the project.'
        self.assertEqual(finish_natural_text(raw),expected)
        self.assertEqual(validate_cleanup(raw,expected),expected)
        for text in ('Do not delete originals, no, I mean delete the copies.',
                     'Use version 12, no, I mean use version 20.',
                     'The string "cancel the project no I mean cancel the subscription" is literal.'):
            self.assertEqual(finish_natural_text(text),text)

    def test_groceries_after_need_to_and_actions_inside_quotes_stay_inline(self):
        for raw in ('I need to buy milk, bread, eggs, rice, and coffee.',
                    'The label "fix login, test updates, write docs" is literal.'):
            self.assertEqual(prepare_layout(raw)[0],raw)

    def test_separate_numbered_lists_restart_without_hiding_changed_numbers(self):
        raw='Two tasks: check login and test updates. Two outputs: queries and report. Keep 12 licenses.'
        text='Two tasks:\n1. Check login.\n2. Test updates.\n\nTwo outputs:\n1. Queries.\n2. Report.\n\nKeep 12 licenses.'
        self.assertTrue(numbers_preserved(raw,text))
        self.assertEqual(validate_cleanup(raw,text),text)
        self.assertFalse(numbers_preserved(raw,text.replace('12 licenses','20 licenses')))
        self.assertFalse(numbers_preserved(raw,text.replace('2. Report','3. Report')))


if __name__=='__main__':unittest.main()
