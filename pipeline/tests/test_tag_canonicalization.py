"""Regressions for alias chains, canonical spelling and safe history repairs."""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tag_canonicalization import (canonical_names, resolve_aliases, resolve_tag_name,
                                  stored_tag_mapping, TagResolutionError)
import db
from processor import process_tags
from merger import compute_voted_tags


class TagCanonicalizationTests(unittest.TestCase):
    def test_chains_and_converging_normalized_aliases(self):
        aliases = resolve_aliases([('Brooklyn Punk','Punk'),('Punk','Punk Rock'),
            ('Stand Up','Stand-up'),('standup','Comedy Show'),('Stand-up','Comedy Show')])
        self.assertEqual(aliases['brooklynpunk'],'Punk Rock')
        self.assertEqual(aliases['standup'],'Comedy Show')

    def test_conflicts_and_cycles_fail(self):
        for pairs in [[('Stand Up','Comedy'),('standup','Music')],
                      [('Benefit','Fundraiser'),('Fundraiser','Benefit')]]:
            with self.assertRaises(TagResolutionError):
                resolve_aliases(pairs)
        with self.assertRaises(TagResolutionError):
            resolve_tag_name('A',{'a':'B','b':'A'})

    def test_unique_curated_spelling_wins_but_curated_collisions_do_not(self):
        names=canonical_names([{'name':'Makerspace','type':'tag'}, {'name':'Maker Space','type':'keyword'},
            {'name':'Foo Bar','type':'tag'},{'name':'Foobar','type':'tag'}])
        self.assertEqual(names['makerspace'],'Makerspace')
        self.assertNotIn('foobar',names)
        self.assertEqual(resolve_aliases([('Maker Space','Makerspace')])['makerspace'],'Makerspace')

    def test_ingestion_resolves_raw_defaults_and_aliases_exposed_by_formatting(self):
        rules={'rewrite':{'brooklynpunk':'Punk','punk':'Punk Rock','outdoors':'Outdoor'},
               'canonical':{'makerspace':'Makerspace'}}
        with patch('processor.city_config.region_tag_token',return_value='NYC'):
            result=process_tags({'hashtags':['BrooklynPunk','MakerSpace','NYCOutdoors']},rules,
                extra_tags=['Outdoors'],ancestor_map={},root_tags=set())
        self.assertEqual(set(result['tags']),{'Punk Rock','Makerspace','Outdoor'})

    def test_alias_to_homonym_uses_event_context(self):
        rules={'rewrite':{'poolnight':'Pool'}}
        ambiguity={'pool':[{'ctx_name':'games','target_name':'Pool / Billiards','priority':10},
                           {'ctx_name':None,'target_name':'Pool / Swimming','priority':0}]}
        result=process_tags({'hashtags':['PoolNight','Games']},rules,ancestor_map={},root_tags=set(),
                            disambiguation_rules=ambiguity)
        self.assertIn('Pool / Billiards',result['tags'])
        self.assertNotIn('Pool',result['tags'])

    def test_history_mapping_preserves_curated_format_and_ambiguous_identities(self):
        tags=[{'name':name,'type':typ} for name,typ in [('Game','tag'),('Games','tag'),
            ('Outdoors','keyword'),('Outdoor','tag'),('Pool','keyword'),('Pool / Swimming','tag')]]
        result=stored_tag_mapping(tags,{'game':'Games','outdoors':'Outdoor','pool':'Pool / Swimming'}, {'pool'})
        self.assertEqual(result,{'Outdoors':'Outdoor'})

    def test_alias_writer_rejects_invalid_update_before_mutation(self):
        cursor=MagicMock()
        cursor.fetchone.return_value=('Music','event')
        cursor.fetchall.return_value=[('Stand Up','Comedy')]
        with self.assertRaises(TagResolutionError):
            db.upsert_tag_alias(cursor,'standup',7)
        self.assertTrue(all(call.args[0].lstrip().startswith('SELECT') for call in cursor.execute.call_args_list))

    def test_alias_export_targets_terminal_tag_and_retains_searchable_spelling(self):
        cursor=MagicMock()
        cursor.fetchall.return_value=[('Punk','Brooklyn Punk','event'),('Punk Rock','Punk','event')]
        self.assertEqual(db.get_tag_aliases_for_export(cursor), {'Punk Rock':['Brooklyn Punk','Punk']})

    def test_reconciled_duplicate_crawl_rows_do_not_get_multiple_votes(self):
        cursor=MagicMock()
        cursor.fetchall.return_value=[]
        cursor.fetchone.return_value=(9,)
        result=compute_voted_tags(cursor,1,['Outdoor','Outdoor','Outdoor'],{'Outdoor'},{},{'outdoor'})
        self.assertNotIn('Outdoor',result)


if __name__ == '__main__':
    unittest.main()
