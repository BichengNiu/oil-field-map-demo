"""Scene identity/time/footprint constraints, independent of upstream availability."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[1]


class SentinelMapTest(unittest.TestCase):
    def test_scene_filter_rejects_future_wrong_collection_and_neighbor_tile(self):
        node=shutil.which('node')
        if not node:self.skipTest('node unavailable')
        source=(ROOT/'map_satellite.js').read_text()
        section=source[source.index('const sentinelContains'):source.index('const sentinelCloud')]
        script=section+'''
        const context={lat:26,lon:56,end:'2026-10-10',cloud:30};
        const base={id:'source-item',collection:'sentinel-2-l2a',
          geometry:{type:'Polygon',coordinates:[[[55,25],[57,25],[57,27],[55,27],[55,25]]]},
          bbox:[55,25,57,27],assets:{visual:{}},properties:{datetime:'2026-10-09T06:00:00Z','eo:cloud_cover':10}};
        const assert=(condition,label)=>{if(!condition)throw new Error(label)};
        assert(sentinelScene(base,context).id==='source-item','valid');
        assert(!sentinelScene({...base,collection:'other'},context),'wrong collection');
        assert(!sentinelScene({...base,assets:{}},context),'no visual');
        assert(!sentinelScene({...base,properties:{datetime:'2099-01-01T00:00:00Z'}},context),'future');
        assert(!sentinelScene({...base,properties:{datetime:'2026-10-11T00:00:00Z'}},context),'after cutoff');
        assert(!sentinelScene(base,{...context,lon:58}),'neighbor tile');
        assert(!sentinelScene(base,{...context,cloud:5}),'cloud threshold');
        const hole={...base,geometry:{type:'Polygon',coordinates:[base.geometry.coordinates[0],[[55.5,25.5],[56.5,25.5],[56.5,26.5],[55.5,26.5],[55.5,25.5]]]}};
        assert(!sentinelScene(hole,context),'footprint hole');
        '''
        result=subprocess.run([node],input=script,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
