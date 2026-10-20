import json
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock

from localflow.config import Config
from localflow.engines import EngineError,validate_cleanup,cleanup_insertion_ready
from localflow.formatting import preserved_cleanup
from localflow.natural_layout import Passage,prepare_layout,checked_items,layout_retained
from localflow.resident import ResidentModels


class NaturalLayoutTests(unittest.TestCase):
    SOURCE=('The app contains tools such as lang graph python and lang chain sql power bi agents and planner '
            'the main purpose is analysis. It gives three files the first one is SQL queries '
            'the second one will be the second one will be a Power BI file and the third one is a report.')

    def test_unpunctuated_tools_and_ordinal_outputs_keep_the_explanation(self):
        text,anchors=prepare_layout(self.SOURCE)
        self.assertEqual(sum(line.startswith('- ') for line in text.splitlines()),0)
        self.assertIn('lang graph, python, lang chain, sql, power bi, agents, planner',text)
        self.assertIn('the main purpose is analysis. It gives three files',text)
        self.assertIn('1. SQL queries\n2. a Power BI file\n3. a report.',text)
        self.assertNotIn('second one',text)
        self.assertEqual(validate_cleanup(self.SOURCE,text),text)
        self.assertTrue(layout_retained(text,text,anchors))

    def test_user_multiword_vocabulary_protects_boundaries_without_changing_spelling(self):
        text,_=prepare_layout('Our dependencies include Alpha Kit Beta Works and Delta Suite.',vocabulary=['Alpha Kit','Beta Works','Delta Suite'])
        self.assertIn('Alpha Kit, Beta Works, Delta Suite',text)
        self.assertFalse(text.startswith('- '))

    def test_explicit_bullet_style_takes_precedence_over_ordinal_item_words(self):
        text,_=prepare_layout('Make a bullet list. First item milk. Second item bread.')
        self.assertIn('- milk.\n- bread.',text)
        self.assertNotIn('1. ',text)

    def test_unknown_items_can_use_a_source_checked_local_model_partition(self):
        splitter=Mock(return_value=json.dumps(['fast search','local cleanup','private storage']))
        text,_=prepare_layout('The features include fast search local cleanup and private storage.',splitter)
        self.assertIn('- fast search\n- local cleanup\n- private storage',text)
        splitter.assert_called_once()
        for proposed in (['fast search','invented feature','private storage'],['fast','and','private storage'],['private storage','fast search']):
            self.assertEqual(checked_items('fast search local cleanup and private storage.',proposed),[])

    def test_prose_code_quotes_and_numeric_literals_are_not_split(self):
        for raw in ('We use Python and SQL to analyze files.',
                    'The first one is ready.',
                    'The first one is red and the third one is blue.',
                    'The string "tools include Python SQL and Excel" is literal.',
                    'Use `the first one is red the second one is blue` as a label.',
                    'The tools include fn(a, b), query(c, d), parser(e, f).',
                    'The items include ₹5,000, ₹6,000 and ₹7,000.',
                    'The dates include 20/10/2026, 21/10/2026 and 22/10/2026.'):
            with self.subTest(raw=raw):self.assertEqual(prepare_layout(raw)[0],raw)

    def test_summary_that_drops_tools_or_explanation_is_not_accepted(self):
        text,anchors=prepare_layout(self.SOURCE)
        self.assertFalse(layout_retained(text,'An app for data analysis.',anchors))
        with self.assertRaises(EngineError):validate_cleanup(self.SOURCE,text.replace('python, ',''))
        self.assertFalse(layout_retained(text,text.replace('the main purpose is analysis. It gives three files','It works.'),anchors))

    def test_model_failure_keeps_safe_natural_layout_and_explicit_paragraph_commands(self):
        text,warning=preserved_cleanup(self.SOURCE,'Model unavailable.')
        self.assertIn('1. SQL queries',text);self.assertIn('lang graph, python, lang chain',text)
        self.assertTrue(cleanup_insertion_ready(self.SOURCE,text,warning,Config(cleanup_enabled=True)))
        text,_=preserved_cleanup('Hello. Next paragraph. Goodbye.','Model unavailable.')
        self.assertEqual(text,'Hello.\n\nGoodbye.')

    def test_resident_final_context_rejects_a_summary_and_preserves_lists(self):
        c=Config(cleanup_enabled=True);runtime=ResidentModels(c,Path('.'));self.addCleanup(runtime.close)
        runtime.qwen=SimpleNamespace(request=Mock(return_value={'content':'This app helps with analysis.'}),close=lambda:None)
        text,warning=runtime.clean(Passage(self.SOURCE),c,threading.Event())
        self.assertIn('lang graph, python, lang chain',text);self.assertIn('1. SQL queries',text)
        self.assertTrue(cleanup_insertion_ready(self.SOURCE,text,warning,c))


if __name__=='__main__':unittest.main()
