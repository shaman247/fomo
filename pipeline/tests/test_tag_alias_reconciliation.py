import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[2]/'scripts/reconcile_tag_aliases.py'
spec=importlib.util.spec_from_file_location('reconcile_tag_aliases',path)
repair=importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


class AliasRepairTests(unittest.TestCase):
    def test_cycles_require_explicit_reviewed_removal(self):
        tags=[{'id':1,'name':'Benefit','type':'tag'}, {'id':2,'name':'Fundraiser','type':'tag'}]
        aliases=[{'alias':'Benefit','tag_id':2},{'alias':'fundraiser','tag_id':1}]
        with self.assertRaises(ValueError):repair.alias_plan(tags,aliases,[])
        resolved,changes=repair.alias_plan(tags,aliases,['Benefit'])
        self.assertEqual(resolved,{'fundraiser':'Benefit'})
        self.assertEqual(changes,[])
        with self.assertRaises(ValueError):repair.alias_plan(tags,aliases,['Nonexistent'])

    def test_plan_flattens_alias_ids_but_does_not_delete_tag_rows(self):
        tags=[{'id':1,'name':'Punk','type':'keyword'}, {'id':2,'name':'Punk Rock','type':'tag'}]
        aliases=[{'alias':'Brooklyn Punk','tag_id':1},{'alias':'Punk','tag_id':2}]
        resolved,changes=repair.alias_plan(tags,aliases,[])
        self.assertEqual(resolved['brooklynpunk'],'Punk Rock')
        self.assertEqual(changes,[{'alias':'Brooklyn Punk','from_id':1,'to_id':2}])
        self.assertEqual(len(tags),2)


if __name__=='__main__':unittest.main()
