"""Local aggregates and the pinned Ts rendering retain calendar gaps."""
from contextlib import contextmanager
from datetime import date
import unittest
from unittest.mock import patch

import duckdb
import data_store
import port_charts
from portwatch_records import SHIP_TYPES


class PortChartsTest(unittest.TestCase):
    def test_sql_complete_coverage_zero_gaps_invalid_values_and_cutoff(self):
        conn=duckdb.connect(':memory:')
        conn.execute(data_store.SCHEMA)
        @contextmanager
        def connection():
            yield conn
        rows=[]
        for day in ('2026-10-01','2026-10-02','2026-10-04','2026-10-05'):
            for pid in ('port1','port2'):
                record={'portid':pid,'date':day,'portcalls':0,
                        **{f'portcalls_{kind}':0 for kind in SHIP_TYPES}}
                if day=='2026-10-02' and pid=='port2':continue
                if day=='2026-10-04':
                    record['portcalls']=3
                    record['portcalls_tanker']=3 if pid=='port1' else -1
                rows.append(record)
        data_store.save_portwatch('ports',rows,'test',conn=conn)
        with patch('data_store.connect',connection):
            result=data_store.portwatch_daily_totals(('port1','port2','port1'),date(2026,10,4))
        self.assertEqual([r['date'] for r in result],[date(2026,10,i) for i in range(1,5)])
        self.assertEqual(result[0]['portcalls'],0)
        self.assertIsNone(result[1]['portcalls'])
        self.assertIsNone(result[2]['portcalls'])
        self.assertEqual(result[3]['portcalls'],6)
        self.assertIsNone(result[3]['portcalls_tanker'])
        conn.close()

    def test_chart_calls_ts_and_keeps_missing_day_in_line(self):
        from Ts.TsPlots import plot_series
        import matplotlib.pyplot as plt
        seen=[]
        def plot(*args,**kwargs):
            figure,ax=plot_series(*args,**kwargs)
            seen.append((list(args[0].index.date),ax.lines[0].get_ydata().copy(),len(ax.lines),kwargs))
            return figure,ax
        rows=tuple((date(2026,10,day),*[value]*6) for day,value in [(1,0),(2,None),(3,6)])
        before=plt.get_fignums()
        with patch('Ts.TsPlots.plot_series',side_effect=plot):
            images=port_charts.chart_images.__wrapped__(rows,date(2026,10,1))
        self.assertEqual(len(images),6)
        self.assertTrue(all(image.startswith(b'\x89PNG') for image in images))
        self.assertEqual(len(seen),6)
        self.assertEqual([x[2] for x in seen],[1]*6)
        import numpy as np
        self.assertTrue(np.isnan(seen[0][1][1]))
        self.assertEqual(seen[0][0],[date(2026,10,i) for i in range(1,4)])
        self.assertFalse(seen[1][3]['auto_dual_y'])
        self.assertEqual(plt.get_fignums(),before)
