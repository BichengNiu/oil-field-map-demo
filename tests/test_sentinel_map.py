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

    def test_highres_dates_and_draw_priority_do_not_substitute_newer_coarse_imagery(self):
        node=shutil.which('node')
        if not node:self.skipTest('node unavailable')
        source=(ROOT/'map_satellite.js').read_text()
        section=source[source.index('const highresDate'):source.index('const openHighresView')]
        script=section+"""
        const assert=(condition,label)=>{if(!condition)throw new Error(label)};
        assert(highresDate(20251027)==='2025-10-27','capture date');
        assert(highresDate(null)==='未提供','missing date');
        assert(highresDate(20250230)==='未提供','invalid calendar date');
        const oldFine={SRC_DATE:20200419,SRC_RES:.5,NICE_NAME:'fine',MinMapLevel:12,MaxMapLevel:18,DrawOrder:80};
        const newCoarse={SRC_DATE:20261017,SRC_RES:15,NICE_NAME:'coarse',MinMapLevel:0,MaxMapLevel:19,DrawOrder:70};
        assert(highresRecords([oldFine,newCoarse],18)[0].SRC_DATE===20200419,'draw priority, not newest date');
        assert(highresRecords([oldFine,newCoarse],5)[0].NICE_NAME==='coarse','zoom-specific source');
        assert(highresRecords([oldFine],19).length===0,'no inferred zoom metadata');
        const secondFine={...oldFine,NICE_NAME:'other',SRC_DATE:20250101};
        assert(highresRecords([oldFine,oldFine,secondFine],18).length===2,'keep ambiguous equal-priority sources');
        """
        result=subprocess.run([node],input=script,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
