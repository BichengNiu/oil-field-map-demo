"""Port views share calendar-week counts, missingness and operating status."""
from datetime import date, timedelta
import unittest
from unittest.mock import patch

import dashboard_rows
import portwatch
from map_popups import port_popup
from portwatch_records import PORT_METRICS


class PortPopupTest(unittest.TestCase):
    def week(self, day=date(2026,10,9), missing_day=False):
        rows = {day - timedelta(days=i): {**{field:0 for field in PORT_METRICS},
                'portcalls': i+1, 'portcalls_tanker':i+1} for i in range(7)}
        if missing_day:
            rows.pop(day-timedelta(days=1))
        with patch('portwatch._activity_rows', return_value={'port105':rows}):
            return portwatch.week_to_date_activity.__wrapped__(day,('port105',))['port105']

    def test_calendar_week_excludes_previous_week_and_popup_is_compact(self):
        weekly = self.week()
        self.assertEqual(weekly['week_start'],'2026-10-05')
        self.assertEqual(weekly['week_calls'],15)
        port = {**weekly,'name':'Das Island','name_cn':'达斯岛港','has_data':True,
                'portcalls':1,'port_operating_status':'normal','port_operating_status_as_of':'2026-10-09'}
        html = port_popup(port,'2026-10-09')
        for text in ('达斯岛港（Das Island）','正常','当日进港艘次','本周累计艘次','15 艘次','15艘次（100.0%）','width:100.0%'):
            self.assertIn(text,html)
        for text in ('class="basis"','class="country"','class="source"','活动指数','过去7天','风险运力','统计覆盖'):
            self.assertNotIn(text,html)
        self.assertEqual(html.count('class="mix-row"'),5)
        self.assertEqual(self.week(date(2026,10,12))['week_calls'],1)
        self.assertEqual(self.week(date(2026,1,1))['week_start'],'2025-12-29')
        self.assertEqual(self.week(date(2026,1,1))['week_calls'],10)

    def test_gap_is_missing_and_zero_calls_do_not_imply_closed(self):
        weekly = self.week(missing_day=True)
        self.assertIsNone(weekly['week_calls'])
        html = port_popup({**weekly,'name':'Test','has_data':True,'portcalls':0},'2026-10-09')
        self.assertIn('未知',html)
        self.assertIn('0 艘次',html)
        self.assertIn('本周累计艘次</span><strong>— 艘次',html)
        self.assertNotIn('停运',html)
        html = port_popup({'name':'Test','port_operating_status':'closed','port_operating_status_as_of':'2026-10-10'},'2026-10-09')
        self.assertIn('未知',html)
        self.assertIn('停运',port_popup({'name':'Test','port_operating_status':'closed'},'2026-10-09'))

    def test_table_order_chinese_country_and_weighted_metric_shares(self):
        one={'statistics_available':True,'has_data':True,'portcalls':1,'week_calls':9,
             **{f'week_calls_{kind}':9 if kind=='tanker' else 0 for kind in portwatch.SHIP_TYPES}}
        two={**one,'portcalls':2,'week_calls':91,'week_calls_tanker':0,'week_calls_container':91}
        no_stats={'statistics_available':False,'portcalls':999,'week_calls':999}
        metrics=dict(dashboard_rows.port_metrics([one,two,no_stats]))
        self.assertEqual(len(metrics),8)
        self.assertEqual(metrics['港口总数'],3)
        self.assertEqual(metrics['当日进港艘次'],'3')
        self.assertEqual(metrics['本周累计艘次'],'100')
        self.assertEqual(metrics['本周油轮/液货船艘次/占比'],'9（9.0%）')
        rows=dashboard_rows.port_rows([{**one,'name':'Dubai','name_cn':'迪拜港','country':'United Arab Emirates'}],date(2026,10,9))
        self.assertEqual(list(rows[0]),['港口名','国家','水域','日期','经营状态','当日进港艘次','本周累计艘次',
            '本周集装箱船累计艘次','本周干散货船累计艘次','本周普通货船累计艘次','本周滚装船累计艘次','本周油轮/液货船累计艘次','本月累计艘次','本月集装箱船累计艘次','本月干散货船累计艘次','本月普通货船累计艘次','本月滚装船累计艘次','本月油轮/液货船累计艘次','纬度','经度','来源'])
        self.assertEqual(rows[0]['国家'],'阿联酋')
        self.assertEqual(rows[0]['经营状态'],'未知')
        self.assertEqual(rows[0]['港口名'],'迪拜港（Dubai）')


    def test_month_cumulative_and_seven_daily_positive_reports_establish_normal(self):
        from portwatch_records import port_status_label
        day=date(2026,6,29)
        rows={day-timedelta(days=i):{**{field:0 for field in PORT_METRICS},'portcalls':2,'portcalls_tanker':2} for i in range(29)}
        with patch('portwatch._activity_rows',return_value={'port105':rows}):
            result=portwatch.week_to_date_activity.__wrapped__(day,('port105',))['port105']
        self.assertEqual(result['month_calls'],58)
        self.assertEqual(result['month_calls_tanker'],58)
        self.assertEqual(result['week_calls'],2)
        self.assertEqual(port_status_label(result,day),'正常')
        self.assertEqual(port_status_label(result,day-timedelta(days=1)),'未知')
        self.assertEqual(port_status_label({**result,'port_operating_status':'closed'},day),'停运')
        rows.pop(day-timedelta(days=12))
        with patch('portwatch._activity_rows',return_value={'port105':rows}):
            result=portwatch.week_to_date_activity.__wrapped__(day,('port105',))['port105']
        self.assertIsNone(result['month_calls'])
        self.assertEqual(result['week_calls'],2)
        self.assertEqual(port_status_label(result,day),'正常')
        rows[day]['portcalls']=0
        with patch('portwatch._activity_rows',return_value={'port105':rows}):
            result=portwatch.week_to_date_activity.__wrapped__(day,('port105',))['port105']
        self.assertEqual(port_status_label(result,day),'未知')
