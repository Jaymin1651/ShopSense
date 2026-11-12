"""Excel business report with native charts (openpyxl)."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

INK, TEAL, SURFACE = '1C2433', '0E7C7B', 'F3F5F8'
HEAD_FONT = Font(bold=True, color='FFFFFF')
HEAD_FILL = PatternFill('solid', fgColor=INK)
MONEY, PCT, INT = '#,##0.00', '0.0', '#,##0'


def _table(ws, start_row: int, headers: list[str], rows: list[list], formats: dict[int, str] | None = None) -> int:
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=start_row, column=c, value=h)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
        cell.alignment = Alignment(vertical='center')
    for r, row in enumerate(rows, start_row + 1):
        for c, value in enumerate(row, 1):
            cell = ws.cell(row=r, column=c, value=value)
            if formats and c in formats and isinstance(value, (int, float)):
                cell.number_format = formats[c]
    return start_row + len(rows)


def _widths(ws, widths: list[int]):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _title(ws, text: str, sub: str):
    ws['A1'] = text
    ws['A1'].font = Font(bold=True, size=16, color=INK)
    ws['A2'] = sub
    ws['A2'].font = Font(color='5A6478')


def build_workbook(data: dict) -> bytes:
    wb = Workbook()
    k = data['kpis']
    g = data['revenue']['growth']

    ws = wb.active
    ws.title = 'Summary'
    _title(ws, 'ShopSense business report', f"{data['scope']} · generated {data['generated_at']}")
    rows = [['Gross merchandise value', k['gmv']], ['Orders', k['orders']], ['Average order value', k['average_order_value']],
            ['Customers who bought', k['customers']], ['Units sold', k['units_sold']],
            ['GMV, last 30 days', g['last_30_days_gmv']], ['Growth vs previous 30 days (%)', g['growth_30d_pct']],
            ['Month-over-month growth (%)', g['month_over_month_pct']],
            ['Products', k['products']], ['Low-stock products', k['low_stock_products']],
            ['Out-of-stock products', k['out_of_stock_products']]]
    _table(ws, 4, ['Metric', 'Value'], rows, {2: MONEY})
    for r in range(5, 5 + len(rows)):
        if ws.cell(row=r, column=1).value in ('Orders', 'Customers who bought', 'Units sold', 'Products',
                                               'Low-stock products', 'Out-of-stock products'):
            ws.cell(row=r, column=2).number_format = INT
    _widths(ws, [34, 18])

    ws = wb.create_sheet('Monthly revenue')
    monthly = data['revenue']['monthly']
    end = _table(ws, 1, ['Month', 'GMV', 'Orders', 'AOV', 'Growth %'],
                 [[m['period'], m['gmv'], m['orders'], m['aov'], m['growth_pct']] for m in monthly],
                 {2: MONEY, 3: INT, 4: MONEY, 5: PCT})
    if monthly:
        chart = LineChart()
        chart.title, chart.y_axis.title, chart.height, chart.width = 'GMV by month', 'GMV', 8, 18
        chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=end), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=end))
        chart.series[0].graphicalProperties.line.solidFill = TEAL
        ws.add_chart(chart, 'G2')
    ws.freeze_panes = 'A2'
    _widths(ws, [12, 16, 10, 12, 11])

    ws = wb.create_sheet('Categories')
    cats = data['revenue']['categories']
    end = _table(ws, 1, ['Category', 'Parent', 'GMV (90 days)', 'Share %', 'Growth %'],
                 [[c['category'], c['parent'], c['gmv'], c['share_pct'], c['growth_pct']] for c in cats],
                 {3: MONEY, 4: PCT, 5: PCT})
    if cats:
        chart = BarChart()
        chart.type, chart.title, chart.height, chart.width = 'bar', 'GMV by category (90 days)', 8, 16
        chart.add_data(Reference(ws, min_col=3, min_row=1, max_row=end), titles_from_data=True)
        chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=end))
        chart.series[0].graphicalProperties.solidFill = TEAL
        ws.add_chart(chart, 'G2')
    _widths(ws, [18, 16, 16, 10, 10])

    ws = wb.create_sheet('Vendor benchmark')
    b = data['benchmark']
    if data['vendor_id'] is None:
        _table(ws, 1, ['Rank', 'Vendor', 'GMV (90 days)', 'Share %', 'Growth %', 'AOV', 'Repeat rate %', 'Score'],
               [[v['rank'], v['vendor'], v['gmv'], v['share_pct'], v['growth_pct'], v['aov'], v['repeat_rate_pct'],
                 v['score']] for v in b['vendors']], {3: MONEY, 4: PCT, 5: PCT, 6: MONEY, 7: PCT})
        _widths(ws, [7, 24, 16, 10, 10, 12, 14, 8])
    else:
        you, m = b.get('you') or {}, b['marketplace']
        _table(ws, 1, ['Measure', 'You', 'Marketplace median'],
               [['GMV (90 days)', you.get('gmv'), m.get('median_gmv')], ['Growth %', you.get('growth_pct'), m.get('median_growth_pct')],
                ['AOV', you.get('aov'), m.get('median_aov')], ['Repeat rate %', you.get('repeat_rate_pct'), m.get('median_repeat_rate_pct')],
                ['Rank', you.get('rank'), None], ['Score (0-100)', you.get('score'), None]], {2: MONEY, 3: MONEY})
        _widths(ws, [20, 16, 20])

    ws = wb.create_sheet('Customers')
    ci = data['customers']
    if ci.get('available'):
        r = _table(ws, 1, ['Churn risk', 'Customers'], [[k_, v] for k_, v in ci['risk_counts'].items()])
        r = _table(ws, r + 2, ['Segment', 'Customers', 'Avg churn probability', 'Expected value, 12 months'],
                   [[s['segment'], s['customers'], s['avg_churn'], s['value_12m']] for s in ci['by_segment']],
                   {3: '0.00', 4: MONEY})
        _table(ws, r + 2, ['Customer', 'Segment', 'Orders', 'Total spent', 'Days since order', 'Churn probability'],
               [[c['customer_id'], c['segment'], c['orders'], c['total_spent'], c['recency_days'], c['churn_probability']]
                for c in ci['high_risk_customers']], {4: MONEY, 6: '0.00'})
        _widths(ws, [16, 14, 20, 24, 16, 18])
    else:
        ws['A1'] = ci.get('reason', 'Not enough customers yet.')

    ws = wb.create_sheet('Segment picks')
    rows = [[s['segment'], p['product'], p['category'], p['lift'], p['segment_buyers_pct']]
            for s in data['segment_recommendations'] for p in s['recommendations']]
    _table(ws, 1, ['Segment', 'Product', 'Category', 'Lift', 'Segment buyers %'], rows, {4: '0.00', 5: PCT})
    _widths(ws, [16, 24, 16, 8, 18])

    ws = wb.create_sheet('Forecast & reorder')
    f = data['forecast']
    r = _table(ws, 1, ['Product', 'In stock', f"Forecast, {f['weeks']} weeks", 'Projected stock', 'Shortfall'],
               [[p['name'], p['current_stock'], p['forecast_units'], p['projected_stock'], p['shortfall']]
                for p in f['products']], {3: '0.0', 4: '0.0', 5: '0.0'})
    _table(ws, r + 2, ['Reorder: product', 'In stock', 'Units/day', 'Lead time', 'Order qty'],
           [[p['name'], p['current_stock'], p['daily_demand'], p['lead_time_days'], p['reorder_qty']] for p in data['reorder']],
           {3: '0.00'})
    ws.freeze_panes = 'A2'
    _widths(ws, [24, 10, 18, 16, 10])

    for sheet in wb.worksheets:
        sheet.sheet_view.showGridLines = sheet.title != 'Summary'
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
