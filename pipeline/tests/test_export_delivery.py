"""Export delivery evidence without changing physical organizer identity."""
import json,sys,tempfile,unittest
from contextlib import ExitStack,redirect_stdout
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import io
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import exporter

TODAY=date(2026,9,23)
LABELS=['Online (Zoom)','Online & In-Person','Via Zoom Platform','Organizer raw spelling','Zoom Room Dog Training',None]
VENUES=['Organizer Center']*4+['Zoom Room','Organizer Center']
EXPECTED=LABELS[:3]+['Organizer Center','Zoom Room','Organizer Center']

class Cursor:
    def execute(self,sql,args=()):
        self.rows=[]
        if 'FROM events e' in sql:
            for i,(label,venue) in enumerate(zip(LABELS,VENUES),1):
                if 'e.archived\n' in sql:
                    self.rows.append((i,'Class',None,'Description','🌐','Class',label,None,None,100+i,venue,'Address',40.,-73.,0))
                else:
                    self.rows.append((i,'Class',None,'Description','🌐',label,None,venue,40.,-73.,'Events',None,100+i,'Address','Class'))
        elif 'FROM event_occurrences' in sql:
            if 'WHERE event_id IN' in sql:self.rows=[(i,TODAY,'6pm',None,'8pm') for i in range(1,7)]
            else:self.rows=[(TODAY,'6pm',None,'8pm')]
        elif 'FROM event_urls' in sql:self.rows=[(i,f'https://example.test/event/{i}') for i in range(1,7)]
        elif 'FROM locations' in sql:
            self.rows=[(100+i,v,40.,-73.,None,None,'Address',None,None,None) for i,v in enumerate(VENUES,1)]
    def fetchall(self):return self.rows

class ExportDeliveryTests(unittest.TestCase):
    def run_export(self,public):
        with tempfile.TemporaryDirectory() as temp,ExitStack() as stack:
            root=Path(temp);(root/'pipeline').mkdir()
            stack.enter_context(redirect_stdout(io.StringIO()))
            stack.enter_context(patch.object(exporter,'SCRIPT_DIR',str(root/'pipeline')))
            stack.enter_context(patch.object(exporter,'get_active_date_window',return_value=(TODAY,TODAY+timedelta(days=90))))
            for name in ['load_assignments','export_contexts','_load_parent_map','_load_source_sites']:
                stack.enter_context(patch.object(exporter,name,return_value={}))
            stack.enter_context(patch.object(exporter.db,'get_tag_hierarchy_for_export',return_value=[]))
            stack.enter_context(patch('tag_hierarchy_policy.validate_hierarchy'))
            if public:
                exporter.export_public_datasets(Cursor(),export_dir=str(root/'public'),export_date=TODAY)
                events=[json.loads(s) for s in (root/'public'/f'events-upcoming-{TODAY}.ndjson').read_text().splitlines()]
                self.assertEqual([e['location']['name'] for e in events],EXPECTED)
                for i,e in enumerate(events,1):
                    self.assertEqual(e['location']['location_id'],100+i)
                    self.assertEqual((e['location']['lat'],e['location']['lng']),(40.,-73.))
                    self.assertEqual(e['location']['address'],'Address')
            else:
                exporter.export_events(Cursor())
                events=json.loads((root/'src/data/events.day0.json').read_text())
                self.assertEqual([e['location'] for e in events],EXPECTED)
                for i,e in enumerate(events,1):
                    self.assertEqual((e['place_id'],e['lat'],e['lng']),(100+i,40.,-73.))
                    self.assertEqual(e['occurrences'],[[str(TODAY),'6pm',None,'8pm']])
                venues=json.loads((root/'src/data/locations.day0.json').read_text())
                self.assertEqual([v['name'] for v in venues],VENUES)
    def test_frontend_chunks_preserve_delivery_and_organizer_pin(self):self.run_export(False)
    def test_public_dataset_preserves_delivery_and_organizer_pin(self):self.run_export(True)
