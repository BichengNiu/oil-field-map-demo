"""Compact port metrics preserve missingness and evidence-based operating status."""
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import portwatch
from map_popups import port_popup
from portwatch_records import PORT_METRICS


class PortPopupTest(unittest.TestCase):
    def roll(self, missing_day=False):
        day = date(2026,10,9)
        rows = {day - timedelta(days=i): {**{field:0 for field in PORT_METRICS},
                'portcalls': i+1, 'portcalls_tanker':i+1} for i in range(6 if missing_day else 7)}
        with patch('portwatch._activity_rows', return_value={'port105':rows}):
            return portwatch.rolling_activity.__wrapped__(day,('port105',),7)['port105']

    def test_seven_day_total_is_complete_sum_not_rounded_average_and_popup_is_compact(self):
        rolling = self.roll()
        self.assertEqual(rolling['window_calls'],28)
        port = {**rolling,'name':'Das Island','name_cn':'达斯岛港','has_data':True,
                'portcalls':1,'port_operating_status':'normal','port_operating_status_as_of':'2026-10-09'}
        html = port_popup(port,'2026-10-09')
        for text in ('达斯岛港（Das Island）','正常','当日进港艘次','过去7天进港艘次','28 艘次','28艘次（100.0%）','width:100.0%'):
            self.assertIn(text,html)
        for text in ('class="basis"','class="country"','class="source"','活动指数','估算装卸','风险运力','统计覆盖','坐标来源'):
            self.assertNotIn(text,html)
        self.assertEqual(html.count('class="mix-row"'),5)

    def test_gap_is_missing_and_zero_calls_do_not_imply_closed(self):
        rolling = self.roll(missing_day=True)
        self.assertIsNone(rolling['window_calls'])
        html = port_popup({**rolling,'name':'Test','has_data':True,'portcalls':0},'2026-10-09')
        self.assertIn('待核实',html)
        self.assertIn('0 艘次',html)
        self.assertIn('过去7天进港艘次</span><strong>— 艘次',html)
        self.assertNotIn('停运',html)
        html = port_popup({'name':'Test','port_operating_status':'closed','port_operating_status_as_of':'2026-10-10'},'2026-10-09')
        self.assertIn('待核实',html)
        self.assertIn('停运',port_popup({'name':'Test','port_operating_status':'closed'},'2026-10-09'))
